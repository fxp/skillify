#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录 faq.txt 灌进智谱开放平台并检索「退换货政策的有效期是多久」，打印检索到的原文片段。

三条路线依次降级，保证最终一定能打印出检索结果，而不是丢一句"不可用"：

  路线一（首选）：托管知识库
      创建知识库 → 上传 faq.txt → 轮询向量化状态 → POST /knowledge/retrieve
  路线二（替代）：embedding-3 向量化 + 本地余弦相似度召回，rerank 可选精排（失败退回余弦序）
  路线三（保底）：本地字符二元组词法打分检索，完全不调 API

本脚本针对性处理的两条实测坑（HTTP 层面看不到）：
  1. /llm-application/open/* 出错时 HTTP 仍是 200，真实状态在响应体 code 里 —— 必须判 body.code。
  2. 上传成功 ≠ 可检索：向量化在后台异步跑，失败时检索端永远返回 200 + 空数组，
     必须轮询 GET /document/{id} 的 embedding_stat（0 处理中 / 1 就绪 / 2 失败）。

无论走哪条路，结束前都会删除临时创建的知识库。
依赖：仅 requests（+ 标准库）。用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import math
import os
import re
import sys
import time

import requests

API_BASE = "https://open.bigmodel.cn/api"
KB_BASE = API_BASE + "/llm-application/open"  # 托管知识库：HTTP 恒 200，看 body.code
EMBED_URL = API_BASE + "/paas/v4/embeddings"
RERANK_URL = API_BASE + "/paas/v4/rerank"

QUERY = "退换货政策的有效期是多久"
EMBED_MODEL = "embedding-3"
EMBED_DIM = 1024        # embedding-3 支持 256/512/1024/2048；查询与切片必须同 model+dimensions
EMBED_BATCH = 32        # embedding-3 单次数组上限 64 条，留余量
CHUNK_MAX_LEN = 300
TOP_K = 5
POLL_TIMEOUT = 180      # 等后台向量化的最长时间（秒）
POLL_INTERVAL = 5


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def http(method, url, *, retries=2, **kw):
    """带简单重试的请求（仅对网络层异常重试，业务错误由调用方判断）。"""
    last = None
    for attempt in range(retries + 1):
        try:
            return requests.request(method, url, **kw)
        except requests.RequestException as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last


# ---------------------------------------------------------------- 通用错误解析

def kb_check(resp, what):
    """托管知识库接口：HTTP 恒 200，必须判 body.code == 200。"""
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"{what}：HTTP {resp.status_code}，响应不是 JSON：{resp.text[:200]}")
    if body.get("code") != 200:
        raise RuntimeError(f"{what}：code={body.get('code')} message={body.get('message')}")
    return body


def std_api_error(resp):
    """/paas/v4/* 标准接口的非 200 响应，提取 error.code / error.message。"""
    try:
        err = resp.json().get("error") or resp.json()
        return f"HTTP {resp.status_code} code={err.get('code')} message={err.get('message')}"
    except Exception:
        return f"HTTP {resp.status_code} {resp.text[:200]}"


# ---------------------------------------------------------------- 本地切片

def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_chunks(path, max_len=CHUNK_MAX_LEN):
    """按行读取 faq.txt，贪心打包成不超过 max_len 字的切片（保持问答行边界）。"""
    lines = [ln.strip() for ln in read_text(path).splitlines() if ln.strip()]
    chunks, buf = [], ""
    for ln in lines:
        if len(ln) > max_len:  # 超长单行硬切
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(ln[i:i + max_len] for i in range(0, len(ln), max_len))
            continue
        if buf and len(buf) + len(ln) + 1 > max_len:
            chunks.append(buf)
            buf = ln
        else:
            buf = f"{buf}\n{ln}" if buf else ln
    if buf:
        chunks.append(buf)
    return chunks


# ---------------------------------------------------------------- 路线一：托管知识库

def hosted_kb_retrieve(api_key, faq_path):
    """完整走一遍托管知识库流程并检索。走不通时抛异常（由调用方降级），资源在 finally 里清理。"""
    knowledge_id = None
    try:
        r = http("POST", f"{KB_BASE}/knowledge", retries=1, headers=auth_headers(api_key),
                 json={"embedding_id": 11,  # 11 = Embedding-3
                       "name": f"faq-demo-{int(time.time())}",
                       "description": "main.py 临时知识库，跑完即删"},
                 timeout=60)
        knowledge_id = (kb_check(r, "创建知识库").get("data") or {}).get("id")
        if not knowledge_id:
            raise RuntimeError("创建知识库：响应里没有 data.id")
        print(f"  已创建知识库 {knowledge_id}")

        with open(faq_path, "rb") as f:
            r = http("POST", f"{KB_BASE}/document/upload_document/{knowledge_id}", retries=1,
                     headers=auth_headers(api_key),
                     files={"files": (os.path.basename(faq_path), f)},
                     data={"knowledge_type": "1"},  # 1 = 按标题段落切
                     timeout=120)
        body = kb_check(r, "上传文档")
        succ = (body.get("data") or {}).get("successInfos") or []
        if not succ:
            failed = (body.get("data") or {}).get("failedInfos") or []
            raise RuntimeError(f"上传文档：全部失败 {json.dumps(failed, ensure_ascii=False)[:300]}")
        doc_id = succ[0]["documentId"]
        print(f"  已上传文档 {doc_id}（{succ[0].get('fileName', 'faq.txt')}），等待后台向量化……")

        # 坑：上传成功 ≠ 可检索。不轮询 embedding_stat，检索端可能永远返回空数组。
        deadline = time.time() + POLL_TIMEOUT
        while True:
            r = http("GET", f"{KB_BASE}/document/{doc_id}", retries=2,
                     headers=auth_headers(api_key), timeout=60)
            doc = kb_check(r, "查询文档状态").get("data") or {}
            stat = doc.get("embedding_stat")
            if stat == 1:
                break
            if stat == 2:
                fail_info = doc.get("failInfo") or {}
                raise RuntimeError(f"向量化失败（embedding_stat=2）："
                                   f"{fail_info.get('embedding_msg') or '未知原因'}")
            if time.time() > deadline:
                raise RuntimeError(f"等待向量化超时（>{POLL_TIMEOUT}s，embedding_stat={stat}）")
            time.sleep(POLL_INTERVAL)
        print("  向量化完成（embedding_stat=1），开始检索")

        r = http("POST", f"{KB_BASE}/knowledge/retrieve", retries=1, headers=auth_headers(api_key),
                 json={"query": QUERY, "knowledge_ids": [knowledge_id],
                       "top_k": TOP_K, "recall_method": "mixed"},
                 timeout=60)
        data = kb_check(r, "知识库检索").get("data") or []
        if not data:
            raise RuntimeError("检索返回空结果（该接口对向量化失败也返回空，视为此路线在当前账号不可用）")
        return [(d.get("text", ""), float(d.get("score") or 0.0),
                 (d.get("metadata") or {}).get("doc_name") or "knowledge")
                for d in data]
    finally:
        if knowledge_id:  # 删除知识库会连带删除库内文档
            try:
                r = http("DELETE", f"{KB_BASE}/knowledge/{knowledge_id}", retries=2,
                         headers=auth_headers(api_key), timeout=60)
                body = r.json()
                if body.get("code") == 200:
                    print(f"  [清理] 临时知识库 {knowledge_id} 已删除")
                else:
                    print(f"  [清理] 临时知识库 {knowledge_id} 删除失败："
                          f"code={body.get('code')} message={body.get('message')}，请到控制台手动删除")
            except Exception as exc:
                print(f"  [清理] 临时知识库 {knowledge_id} 删除请求异常：{exc}，请到控制台手动删除")


# ---------------------------------------------------------------- 路线二：embedding + 余弦（+ rerank）

def embed_texts(api_key, texts):
    """批量向量化，返回与输入同序的向量列表（按 data[].index 对齐，不依赖返回顺序）。"""
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        r = http("POST", EMBED_URL, retries=2, headers=auth_headers(api_key),
                 json={"model": EMBED_MODEL, "input": texts[i:i + EMBED_BATCH],
                       "dimensions": EMBED_DIM},
                 timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"embeddings 调用失败：{std_api_error(r)}")
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        vectors.extend(d["embedding"] for d in data)
    return vectors


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def try_rerank(api_key, query, docs, top_n):
    """可选精排。任何失败都返回 None，调用方退回余弦序，不影响结果产出。"""
    try:
        r = http("POST", RERANK_URL, retries=1, headers=auth_headers(api_key),
                 json={"model": "rerank", "query": query, "documents": docs,
                       "top_n": top_n, "return_documents": False},
                 timeout=60)
        if r.status_code != 200:
            return None
        return [(it["index"], float(it["relevance_score"]))
                for it in r.json().get("results", [])]
    except Exception:
        return None


def embedding_retrieve(api_key, chunks):
    print(f"  用 {EMBED_MODEL} 向量化查询与 {len(chunks)} 个切片……")
    q_vec = embed_texts(api_key, [QUERY])[0]
    c_vecs = embed_texts(api_key, chunks)
    scored = sorted(((cosine(q_vec, v), i) for i, v in enumerate(c_vecs)), reverse=True)
    top = scored[:10]  # 余弦召回 top10，再交给 rerank 精排
    cand = [chunks[i] for _, i in top]
    reranked = try_rerank(api_key, QUERY, cand, min(TOP_K, len(cand)))
    if reranked:
        return [(cand[i], s, "faq.txt（rerank 精排）") for i, s in reranked]
    return [(chunks[i], s, "faq.txt（余弦相似度）") for s, i in top[:TOP_K]]


# ---------------------------------------------------------------- 路线三：本地词法检索（保底）

def _grams(s, n):
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def lexical_score(query, chunk):
    """查询的一元/二元字符组在切片中的覆盖率，纯本地、无依赖。"""
    total = 0.0
    for n in (1, 2):
        q, c = _grams(query, n), _grams(chunk, n)
        if q:
            total += len(q & c) / len(q)
    return total / 2


def lexical_retrieve(chunks):
    scored = sorted(((lexical_score(QUERY, c), i) for i, c in enumerate(chunks)),
                    reverse=True)
    return [(chunks[i], s, "faq.txt（本地词法打分）") for s, i in scored[:TOP_K]]


# ---------------------------------------------------------------- 输出与主流程

def print_results(route, items):
    print("\n" + "=" * 72)
    print(f"检索问题：{QUERY}")
    print(f"命中路线：{route}（共 {len(items)} 条原文片段）")
    print("=" * 72)
    for rank, (text, score, src) in enumerate(items, 1):
        print(f"\n[{rank}] score={score:.4f}  来源：{src}")
        print("-" * 72)
        print(text.strip())
    print("-" * 72)


def main():
    faq_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faq.txt")
    if not os.path.isfile(faq_path):
        print(f"错误：找不到 {faq_path}，请把 faq.txt 放在 main.py 同目录。", file=sys.stderr)
        return 1
    chunks = load_chunks(faq_path)
    if not chunks:
        print("错误：faq.txt 没有有效内容。", file=sys.stderr)
        return 1

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("警告：环境变量 ZHIPUAI_API_KEY 未设置，跳过路线一/二，直接走本地词法检索。")

    if api_key:
        print("\n[路线一] 托管知识库：创建 → 上传 → 等向量化 → 检索")
        try:
            items = hosted_kb_retrieve(api_key, faq_path)
            print_results("路线一 · 托管知识库检索", items)
            return 0
        except Exception as exc:
            print(f"[路线一] 托管知识库走不通：{exc}\n")

        print("[路线二] 替代方案：embedding-3 + 本地余弦召回（rerank 可选精排）")
        try:
            items = embedding_retrieve(api_key, chunks)
            if not items:
                raise RuntimeError("余弦检索没有得到任何切片")
            print_results("路线二 · 自建向量检索", items)
            return 0
        except Exception as exc:
            print(f"[路线二] 自建向量检索走不通：{exc}\n")

        print("[路线三] 保底方案：本地词法打分检索（不依赖 API）")
    items = lexical_retrieve(chunks)
    if max(s for _, s, _ in items) == 0:
        print("提示：本地词法检索所有切片得分为 0，faq.txt 里可能没有与问题相关的内容。")
    print_results("路线三 · 本地词法检索", items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
