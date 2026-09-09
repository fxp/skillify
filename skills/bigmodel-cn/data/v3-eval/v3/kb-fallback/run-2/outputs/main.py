#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录 faq.txt 灌进智谱托管知识库，检索「退换货政策的有效期是多久」，
并把检索到的原文片段打印出来。

主路：托管知识库（创建 → 上传 → 轮询向量化状态 → 检索）。
降级：托管知识库任何一步走不通（创建/上传失败、向量化失败或超时、检索为空）时，
      自动改用自建检索，同样打印原文片段：
      ① embeddings 向量召回 + rerank 精排；
      ② 直接用 rerank 对全部分片打分（不依赖 embeddings）；
      ③ 完全离线的本地关键词匹配兜底。
无论走哪条路，结束时都删除本次创建的临时知识库/文档。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests。
"""

import math
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://open.bigmodel.cn/api"
QUESTION = "退换货政策的有效期是多久"
TOP_K = 5
POLL_INTERVAL = 3   # 轮询向量化状态的间隔（秒）
POLL_TIMEOUT = 150  # 等待向量化的总时长（秒）
CHUNK_MAX = 500     # 自建检索的单片段字数上限

API_KEY = os.environ.get("ZHIPUAI_API_KEY", "")


class KBError(RuntimeError):
    """托管知识库族接口的业务失败。

    该族接口（/llm-application/open/*）出错时 HTTP 状态码仍是 200，
    真实结果在响应体 code 字段里，raise_for_status() 永远不会触发。
    """


def auth_headers():
    return {"Authorization": f"Bearer {API_KEY}"}


def find_faq():
    """在脚本目录、当前目录、脚本上级目录里找 faq.txt。"""
    here = Path(__file__).resolve().parent
    for cand in (here / "faq.txt", Path.cwd() / "faq.txt", here.parent / "faq.txt"):
        if cand.is_file():
            return cand
    return None


def read_text(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------- 托管知识库主路

def kb_call(method, path, *, params=None, json_body=None, files=None, data=None):
    """请求 /llm-application/open/* 族接口，校验 body.code == 200 后返回 body。"""
    resp = requests.request(
        method, BASE + path, headers=auth_headers(),
        params=params, json=json_body, files=files, data=data, timeout=60)
    try:
        body = resp.json()
    except ValueError:
        raise KBError(f"{method} {path} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if body.get("code") != 200:
        raise KBError(f"{method} {path} 失败：code={body.get('code')} message={body.get('message')}")
    return body


def wait_embedding_ready(doc_id):
    """轮询文档向量化状态：0=处理中 1=成功 2=失败。

    上传成功不等于可检索，向量化失败时检索端只会返回空数组、不报任何错，
    所以必须在这里等到 embedding_stat == 1。失败（2）时先触发一次重新向量化补救，
    仍失败才放弃并走降级方案。
    """
    retriggered = False
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        data = kb_call("GET", f"/llm-application/open/document/{doc_id}").get("data") or {}
        stat = data.get("embedding_stat")
        if stat == 1:
            print("        embedding_stat = 1，文档已可检索。")
            return
        if stat == 2:
            fail = data.get("failInfo") or {}
            if not retriggered:
                retriggered = True
                print(f"        embedding_stat = 2（{fail.get('embedding_code')} "
                      f"{fail.get('embedding_msg')}），触发一次重新向量化…")
                try:
                    kb_call("POST", f"/llm-application/open/document/embedding/{doc_id}", json_body={})
                except KBError as exc:
                    print(f"        重新向量化请求失败：{exc}")
                deadline = time.time() + 60  # 再给一轮观察窗口
                time.sleep(5)
                continue
            raise KBError(f"向量化失败：embedding_stat=2 {fail}")
        time.sleep(POLL_INTERVAL)
    raise KBError(f"等待向量化完成超时（>{POLL_TIMEOUT}s）")


def kb_retrieve(knowledge_id):
    """检索个人知识库，返回 data 列表；空结果换召回方式各试一次。"""
    for recall in ("mixed", "keyword", "embedding"):
        body = kb_call("POST", "/llm-application/open/knowledge/retrieve", json_body={
            "query": QUESTION,
            "knowledge_ids": [knowledge_id],
            "top_k": TOP_K,
            "top_n": 20,
            "recall_method": recall,
        })
        results = body.get("data") or []
        if results:
            print(f"        recall_method={recall}，召回 {len(results)} 条。")
            return results
        time.sleep(2)
    return []


def cleanup(knowledge_id, doc_id):
    """删除本次创建的临时资源：先删文档，再删知识库（连带库内其余文档）。"""
    if not knowledge_id:
        return
    if doc_id:
        try:
            kb_call("DELETE", f"/llm-application/open/document/{doc_id}")
        except Exception as exc:
            print(f"  [清理] 删除文档 {doc_id} 失败：{exc}")
    try:
        kb_call("DELETE", f"/llm-application/open/knowledge/{knowledge_id}")
        print(f"  [清理] 临时知识库 {knowledge_id} 及其文档已删除。")
    except Exception as exc:
        print(f"  [清理] 删除知识库 {knowledge_id} 失败：{exc}（请到控制台手动删除）")


def run_hosted_kb(faq_path):
    """主路：托管知识库全流程，返回 [(text, score), ...]；失败抛异常（资源在 finally 清理）。"""
    knowledge_id, doc_id = None, None
    try:
        print("主路：智谱托管知识库")
        print("  [1/4] 创建知识库（Embedding-3）…")
        body = kb_call("POST", "/llm-application/open/knowledge", json_body={
            "embedding_id": 11, "embedding_model": "Embedding-3",
            "name": f"faq-demo-{time.strftime('%Y%m%d%H%M%S')}",
            "description": "faq.txt 检索演示（用完即删）",
            "icon": "book",
        })
        knowledge_id = (body.get("data") or {}).get("id")
        if not knowledge_id:
            raise KBError(f"创建知识库未返回 id：{body}")
        print(f"        knowledge_id = {knowledge_id}")

        print("  [2/4] 上传 faq.txt（txt 按标题段落切，knowledge_type=1）…")
        with open(faq_path, "rb") as f:
            body = kb_call("POST", f"/llm-application/open/document/upload_document/{knowledge_id}",
                           files={"files": (faq_path.name, f, "text/plain")},
                           data={"knowledge_type": "1"})
        data = body.get("data") or {}
        succ = data.get("successInfos") or []
        if not succ:
            raise KBError(f"上传失败：{data.get('failedInfos') or body}")
        doc_id = succ[0].get("documentId")
        print(f"        document_id = {doc_id}")

        print("  [3/4] 等待向量化完成（0=处理中 1=成功 2=失败）…")
        wait_embedding_ready(doc_id)

        print("  [4/4] 检索 …")
        results = kb_retrieve(knowledge_id)
        if not results:
            raise KBError("检索持续返回空结果（文档未被正确索引）")
        return [(r.get("text", ""), r.get("score")) for r in results]
    finally:
        cleanup(knowledge_id, doc_id)


# --------------------------------------------------------------- 自建检索降级路

def chunk_faq(text):
    """按空行切段（FAQ 通常一段一个问答对）；超长段再按行聚合；连换行都没有就硬切。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    for para in paras:
        if len(para) <= CHUNK_MAX:
            chunks.append(para)
            continue
        buf = ""
        for line in para.splitlines():
            line = line.strip()
            if not line:
                continue
            if buf and len(buf) + len(line) + 1 > CHUNK_MAX:
                chunks.append(buf)
                buf = line
            else:
                buf = f"{buf}\n{line}" if buf else line
        if buf:
            chunks.append(buf)
    final = []
    for chunk in chunks:
        for i in range(0, len(chunk), CHUNK_MAX):
            final.append(chunk[i:i + CHUNK_MAX])
    return final


def paas_post(path, payload, timeout=120):
    """请求 /paas/v4/* 标准接口（这些接口出错会返回 4xx/5xx + error 字段）。"""
    resp = requests.post(BASE + path, headers=auth_headers(), json=payload, timeout=timeout)
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"{path} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    if resp.status_code != 200 or body.get("error"):
        err = body.get("error") or {}
        raise RuntimeError(f"{path} 失败：HTTP {resp.status_code} "
                           f"code={err.get('code')} message={err.get('message')}")
    return body


def embed_texts(texts):
    """embedding-3 批量向量化（单次请求最多 64 条，分批处理），返回与输入同序的向量。"""
    vecs = []
    for i in range(0, len(texts), 64):
        body = paas_post("/paas/v4/embeddings", {
            "model": "embedding-3",
            "input": texts[i:i + 64],
            "dimensions": 1024,
        })
        data = sorted(body.get("data", []), key=lambda d: d.get("index", 0))
        vecs.extend(d["embedding"] for d in data)
    return vecs


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def rerank_candidates(query, docs, top_n):
    """rerank 精排。results 里默认只有 index 和分数，要拿回原文必须 return_documents=true。"""
    body = paas_post("/paas/v4/rerank", {
        "model": "rerank",
        "query": query,
        "documents": docs,
        "top_n": top_n,
        "return_documents": True,
    })
    out = []
    for item in body.get("results", []):
        idx = item.get("index")
        if isinstance(idx, int) and 0 <= idx < len(docs):
            out.append((docs[idx], item.get("relevance_score", 0.0)))
    return out


def local_keyword_rank(query, docs, top_k):
    """离线兜底：查询与片段的字符 bigram 重合度排序，保证完全不依赖 API 也有结果。"""
    def terms(s):
        grams = set(s)
        grams.update(s[i:i + 2] for i in range(len(s) - 1))
        return grams

    q = terms(query)
    scored = [(len(q & terms(d)) / len(q), d) for d in docs]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(d, s) for s, d in scored[:top_k]]


def run_fallback_retrieval(chunks):
    """托管知识库走不通时的自建检索，返回 ([(text, score), ...], 方案名)。"""
    # ① embeddings 召回 + rerank 精排
    try:
        print("降级方案①：embeddings 向量召回 + rerank 精排")
        q_vec = embed_texts([QUESTION])[0]
        doc_vecs = embed_texts(chunks)
        ranked = sorted(range(len(chunks)), key=lambda i: cosine(q_vec, doc_vecs[i]), reverse=True)
        cand = ranked[:20]
        try:
            results = rerank_candidates(QUESTION, [chunks[i] for i in cand], TOP_K)
            if results:
                return results, "自建检索（embedding 召回 + rerank 精排）"
        except Exception as exc:
            print(f"  rerank 精排失败（{exc}），直接用向量相似度排序。")
        return ([(chunks[i], cosine(q_vec, doc_vecs[i])) for i in cand[:TOP_K]],
                "自建检索（embedding 向量召回）")
    except Exception as exc:
        print(f"降级方案①失败：{exc}")
    # ② 直接 rerank 全量候选（rerank 上限 128 条 / 单条 4096 字符）
    try:
        print("降级方案②：直接用 rerank 对全部分片检索")
        docs = [c[:4000] for c in chunks[:128]]
        results = rerank_candidates(QUESTION, docs, TOP_K)
        if results:
            return results, "自建检索（rerank 全量打分）"
    except Exception as exc:
        print(f"降级方案②失败：{exc}")
    # ③ 本地关键词兜底
    print("降级方案③：本地关键词匹配兜底（离线）")
    return local_keyword_rank(QUESTION, chunks, TOP_K), "本地关键词检索（离线兜底）"


# --------------------------------------------------------------- 输出与入口

def print_results(source, results):
    print(f"\n===== 检索结果（{source}）=====")
    print(f"问题：{QUESTION}")
    for i, (text, score) in enumerate(results, 1):
        score_str = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
        print(f"\n[片段 {i}] score={score_str}\n{text}")
    print()


def main():
    if not API_KEY:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY。")
        return 1
    faq_path = find_faq()
    if faq_path is None:
        print("错误：找不到 faq.txt（脚本目录、当前目录及其上级都找过）。")
        return 1
    text = read_text(faq_path).strip()
    if not text:
        print("错误：faq.txt 是空文件。")
        return 1
    print(f"已读取 {faq_path}（{len(text)} 字）。\n")

    results = None
    try:
        results = run_hosted_kb(faq_path)
    except Exception as exc:
        print(f"\n托管知识库这条路走不通：{exc}")
        print("自动降级为自建检索（不依赖托管知识库）……")
        chunks = chunk_faq(text)
        print(f"faq.txt 切分为 {len(chunks)} 个片段。")
        results, source = run_fallback_retrieval(chunks)
        print_results(source, results)
        return 0

    print_results("智谱托管知识库", results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
