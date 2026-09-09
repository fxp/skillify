#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录 faq.txt 灌进智谱托管知识库，检索「退换货政策的有效期是多久」并打印原文片段。

三级策略，逐级降级，目标是**一定**把检索到的原文片段打印出来：
  方案 A：智谱托管知识库（/llm-application/open/*）
          建库 → 上传 faq.txt → 轮询 embedding_stat 到向量化成功 → 检索
  方案 B：自建检索：/paas/v4/embeddings 向量召回 + /paas/v4/rerank 精排
  方案 C：纯本地字符 bigram 检索，不依赖任何 API（离线兜底）

无论走通哪条路，方案 A 创建的临时知识库都会在 finally 里删除。

两个用真实调用验证过的坑，代码里专门处理了：
  1) 知识库族接口出错时 HTTP 仍是 200，真实状态在 body.code —— 不能只看状态码；
  2) 上传成功 ≠ 可检索：向量化是后台异步的，失败时检索端永远返回 200+空数组，
     必须轮询 GET /document/{id} 的 embedding_stat（0 处理中 / 1 成功 / 2 失败）。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests。
"""

import json
import math
import os
import re
import sys
import time

import requests

BASE = "https://open.bigmodel.cn/api"
QUESTION = "退换货政策的有效期是多久"
TOP_K = 5
HTTP_TIMEOUT = 60      # 单个请求超时（秒）
EMBED_WAIT_FIRST = 120  # 首轮等待向量化（秒）
EMBED_WAIT_RETRY = 60   # 重新向量化后再等一轮（秒）

ROUTE_NAMES = {
    "A": "A 智谱托管知识库（/llm-application/open/knowledge/retrieve）",
    "B": "B 自建检索（embedding-3 召回 + rerank 精排）",
    "C": "C 本地离线检索（字符 bigram 兜底，未用到 API）",
}


def log(msg):
    print(msg, flush=True)


class KbUnavailable(Exception):
    """托管知识库这条路走不通——用来触发降级，不代表脚本失败。"""


def find_faq():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "faq.txt"), os.path.join(os.getcwd(), "faq.txt")):
        if os.path.isfile(path):
            return path
    log(f"[错误] 找不到 faq.txt（找过 {here} 和当前目录）。")
    sys.exit(1)


def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------- 方案 A：托管知识库 ----------------

def kb_call(method, path, api_key, **kw):
    """知识库族接口出错时 HTTP 仍是 200，真实状态在 body.code，必须在这里统一判。"""
    resp = requests.request(
        method, BASE + path,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=HTTP_TIMEOUT, **kw)
    resp.raise_for_status()
    try:
        body = resp.json()
    except ValueError:
        raise KbUnavailable(f"{method} {path} 返回非 JSON: {resp.text[:200]!r}")
    if body.get("code") != 200:
        raise KbUnavailable(
            f"{method} {path} 业务失败 code={body.get('code')} message={body.get('message')}")
    return body


def wait_vectorized(api_key, doc_id, timeout_s):
    """轮询文档详情直到 embedding_stat==1；==2 直接判失败，别指望检索端的空数组能暴露问题。"""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        data = kb_call("GET", f"/llm-application/open/document/{doc_id}", api_key).get("data") or {}
        last = data.get("embedding_stat")
        if last == 1:
            return
        if last == 2:
            fail = data.get("failInfo") or {}
            raise KbUnavailable(
                f"向量化失败 embedding_stat=2 "
                f"(embedding_code={fail.get('embedding_code')} msg={fail.get('embedding_msg')})")
        time.sleep(3)
    raise KbUnavailable(f"等待向量化超时（{timeout_s}s，最后 embedding_stat={last}）")


def hosted_kb_retrieve(api_key, faq_path):
    know_id = None
    try:
        # 1) 建库（embedding_id=11 即 Embedding-3）
        body = kb_call("POST", "/llm-application/open/knowledge", api_key,
                       json={"embedding_id": 11,
                             "name": f"faq临时库-{int(time.time())}",
                             "description": "main.py 检索演示用，脚本结束自动删除"})
        know_id = (body.get("data") or {}).get("id")
        if not know_id:
            raise KbUnavailable(f"创建知识库未返回 id: {json.dumps(body, ensure_ascii=False)[:200]}")
        log(f"[方案A] 知识库已创建: {know_id}")

        # 2) 上传 faq.txt（multipart 字段名必须是 files；knowledge_type=1 按标题段落切）
        with open(faq_path, "rb") as fh:
            body = kb_call("POST", f"/llm-application/open/document/upload_document/{know_id}",
                           api_key,
                           files={"files": (os.path.basename(faq_path), fh, "text/plain")},
                           data={"knowledge_type": "1"})
        infos = (body.get("data") or {}).get("successInfos") or []
        if not infos:
            raise KbUnavailable(f"上传失败: {json.dumps(body, ensure_ascii=False)[:300]}")
        doc_id = infos[0].get("documentId")
        log(f"[方案A] faq.txt 已上传 (documentId={doc_id})，等待后台向量化……")

        # 3) 等向量化就绪；失败先触发一次重新向量化再等一轮（.txt 已是最稳格式，重试是最后手段）
        try:
            wait_vectorized(api_key, doc_id, EMBED_WAIT_FIRST)
        except KbUnavailable as e:
            log(f"[方案A] 首轮向量化未成功（{e}），触发重新向量化后再等一轮……")
            kb_call("POST", f"/llm-application/open/document/embedding/{doc_id}",
                    api_key, json={})
            wait_vectorized(api_key, doc_id, EMBED_WAIT_RETRY)

        # 4) 检索
        log("[方案A] 向量化就绪，开始检索……")
        body = kb_call("POST", "/llm-application/open/knowledge/retrieve", api_key,
                       json={"query": QUESTION, "knowledge_ids": [know_id],
                             "top_k": TOP_K, "recall_method": "mixed"})
        snippets = body.get("data") or []
        if not snippets:
            raise KbUnavailable("向量化已就绪但检索返回空数组")
        return [(item.get("text", ""), item.get("score")) for item in snippets]
    finally:
        # 临时资源清理：删库即连同库内文档一起删除
        if know_id:
            try:
                kb_call("DELETE", f"/llm-application/open/knowledge/{know_id}", api_key)
                log(f"[清理] 临时知识库 {know_id} 及库内文档已删除")
            except Exception as e:
                log(f"[清理] 删除临时知识库 {know_id} 失败: {e}（请到控制台手动删除）")


# ---------------- 方案 B：embeddings 召回 + rerank 精排 ----------------

def chunk_text(text, max_len=400):
    """按空行分段，超长段再按句子边界二次切。"""
    chunks = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_len:
            chunks.append(para)
            continue
        buf = ""
        for sent in re.split(r"(?<=[。！？!?；;\n])", para):
            if buf and len(buf) + len(sent) > max_len:
                chunks.append(buf.strip())
                buf = sent
            else:
                buf += sent
        if buf.strip():
            chunks.append(buf.strip())
    return chunks


def embed_texts(api_key, texts):
    """embedding-3 单次数组上限 64 条，分批；结果按 index 对齐，不假设返回顺序。"""
    vectors = []
    for i in range(0, len(texts), 50):
        resp = requests.post(
            f"{BASE}/paas/v4/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "embedding-3", "input": texts[i:i + 50]},
            timeout=HTTP_TIMEOUT)
        if not resp.ok:
            raise RuntimeError(f"embeddings HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json().get("data") or []
        vectors.extend(item["embedding"] for item in sorted(data, key=lambda x: x.get("index", 0)))
    if len(vectors) != len(texts):
        raise RuntimeError(f"embeddings 返回数量不符（{len(vectors)}/{len(texts)}）")
    return vectors


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rerank_texts(api_key, query, docs, top_n):
    resp = requests.post(
        f"{BASE}/paas/v4/rerank",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "rerank", "query": query, "documents": docs,
              "top_n": top_n, "return_documents": True},
        timeout=HTTP_TIMEOUT)
    if not resp.ok:
        raise RuntimeError(f"rerank HTTP {resp.status_code}: {resp.text[:200]}")
    results = resp.json().get("results") or []
    # results 只有 index 和分数；分数可能并列，不能只信第一名
    return [(docs[r["index"]], r.get("relevance_score"))
            for r in sorted(results, key=lambda r: r.get("relevance_score", 0), reverse=True)
            if isinstance(r.get("index"), int) and 0 <= r["index"] < len(docs)]


def self_built_retrieve(api_key, text):
    chunks = chunk_text(text)
    if not chunks:
        raise RuntimeError("faq.txt 切分后没有内容")
    log(f"[方案B] faq.txt 切成 {len(chunks)} 段，embedding-3 向量召回 + rerank 精排")
    vectors = embed_texts(api_key, [QUESTION] + chunks)
    qvec = vectors[0]
    recalled = sorted(range(len(chunks)),
                      key=lambda i: cosine(qvec, vectors[i + 1]), reverse=True)[:10]
    try:
        ranked = rerank_texts(api_key, QUESTION, [chunks[i] for i in recalled], TOP_K)
        if ranked:
            return ranked
        log("[方案B] rerank 未返回结果，退回向量召回排序")
    except Exception as e:
        log(f"[方案B] rerank 失败（{e}），退回向量召回排序")
    return [(chunks[i], round(cosine(qvec, vectors[i + 1]), 4)) for i in recalled[:TOP_K]]


# ---------------- 方案 C：本地离线兜底 ----------------

def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return [s[i:i + 2] for i in range(max(len(s) - 1, 0))] or ([s] if s else [])


def local_retrieve(text):
    """用问题字符 bigram 在片段中的覆盖率打分。纯本地、零依赖，保证一定有输出。"""
    qset = set(bigrams(QUESTION))
    scored = []
    for idx, chunk in enumerate(chunk_text(text)):
        cset = set(bigrams(chunk)) | set(re.sub(r"\s+", "", chunk))
        score = len(qset & cset) / len(qset) if qset else 0.0
        scored.append((score, idx, chunk))
    scored.sort(key=lambda t: (-t[0], t[1]))
    hits = [(chunk, round(score, 4)) for score, _, chunk in scored[:TOP_K] if score > 0]
    # 一条都没命中时也保证有输出（原始顺序前几段），不返回空列表
    return hits or [(chunk, 0.0) for _, _, chunk in scored[:3]]


# ---------------- 主流程 ----------------

def print_results(route, snippets):
    log("")
    log("=" * 64)
    log(f"检索路线：{ROUTE_NAMES[route]}")
    log(f"问题：{QUESTION}")
    log(f"共检索到 {len(snippets)} 条原文片段：")
    for i, (text, score) in enumerate(snippets, 1):
        log("-" * 64)
        log(f"[{i}] score={score}")
        log(text)
    log("=" * 64)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    faq_path = find_faq()
    text = read_text(faq_path)
    if not text.strip():
        log("[错误] faq.txt 是空的")
        sys.exit(1)

    snippets, route = None, None

    if api_key:
        try:
            snippets = hosted_kb_retrieve(api_key, faq_path)
            route = "A"
        except Exception as e:
            log(f"[方案A] 托管知识库这条路走不通：{e}")
    else:
        log("[提示] 未设置 ZHIPUAI_API_KEY，跳过方案 A/B")

    if snippets is None and api_key:
        log("[降级] 改走方案 B：embeddings 召回 + rerank 精排的自建检索")
        try:
            snippets = self_built_retrieve(api_key, text)
            route = "B"
        except Exception as e:
            log(f"[方案B] 自建检索也不可用：{e}")

    if snippets is None:
        log("[降级] 改走方案 C：本地离线检索，保证把检索到的原文片段打印出来")
        snippets = local_retrieve(text)
        route = "C"

    print_results(route, snippets)


if __name__ == "__main__":
    main()
