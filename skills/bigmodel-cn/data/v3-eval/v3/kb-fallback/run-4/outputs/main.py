#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录 faq.txt 灌进智谱（bigmodel.cn）托管知识库，检索「退换货政策的有效期是多久」，
并把检索到的原文片段打印出来。

主路：托管知识库（创建知识库 → 上传 faq.txt → 轮询向量化 → 检索）。
  实测坑：/llm-application/open/* 这族接口出错时 HTTP 状态码仍是 200，真实结果在
  响应体 code 字段（如 100013 知识库不存在），所以每一步都必须判 code == 200；
  且"上传成功 ≠ 文档可检索"，向量化是后台异步的，必须轮询 GET /document/{id}
  直到 embedding_stat == 1（0 处理中 / 1 成功 / 2 失败）才能去检索。
降级：托管知识库在本账号走不通（创建/上传失败、向量化失败、检索返回空数组）时，
  自动改用 /paas/v4/embeddings 向量召回 + /paas/v4/rerank 精排的自建检索，
  对本地切块后的 faq.txt 原文做真实的语义检索，保证最终一定打印出检索到的原文片段，
  而不是只丢一句"知识库不可用"。
清理：无论走哪条路，托管知识库里的临时文档和知识库都会删除；自建检索方案
  不在服务端创建任何资源，天然无需清理。

依赖：仅 requests（标准库除外）。
运行：ZHIPUAI_API_KEY=你的key python3 main.py
"""

import math
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
QUESTION = "退换货政策的有效期是多久"
FAQ_PATH = Path(__file__).resolve().parent / "faq.txt"

CHUNK_MAX_LEN = 600  # 单块字符数上限，远小于 embedding-3 单条 3072 token 限制
EMBED_BATCH = 32     # embedding-3 单次请求最多 64 条，留余量分批


class ApiError(RuntimeError):
    """接口业务层失败（HTTP 可能仍是 200，真状态在 body.code / error.code）。"""

    def __init__(self, where, code, message):
        super().__init__(f"{where}: code={code}, message={message}")


class HostedKbUnavailable(RuntimeError):
    """托管知识库这条路走不通，需要降级到自建检索。"""


def kb_request(method, path, *, json_body=None, files=None, data=None,
               params=None, timeout=90):
    """调用 /llm-application/open/* 知识库接口族。

    坑：这族接口任何业务错误都返回 HTTP 200（真状态在 body.code），
    raise_for_status() 永远不会触发，必须显式判 code == 200。
    """
    resp = requests.request(
        method, BASE + path, headers=HEADERS, json=json_body,
        files=files, data=data, params=params, timeout=timeout,
    )
    resp.raise_for_status()  # 只兜网关/鉴权层异常，业务错误见下方 code 判断
    body = resp.json()
    if body.get("code") != 200:
        raise ApiError(path, body.get("code"), body.get("message"))
    return body.get("data")


def paas_post(path, payload, timeout=60):
    """调用 /paas/v4/* 标准接口（embeddings / rerank），错误形如 {"error":{...}}。"""
    resp = requests.post(BASE + path, headers=HEADERS, json=payload, timeout=timeout)
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok or "error" in body:
        err = body.get("error") or {}
        raise ApiError(path, err.get("code", resp.status_code),
                       err.get("message", resp.text[:200]))
    return body


# ---------------------------------------------------------------- 主路：托管知识库

def _poll_embedding_stat(doc_id, timeout_s):
    """轮询文档向量化状态：0=处理中 1=成功 2=失败。"""
    deadline = time.time() + timeout_s
    stat, fail_info = None, {}
    while time.time() < deadline:
        try:
            detail = kb_request("GET", f"/llm-application/open/document/{doc_id}") or {}
            stat = detail.get("embedding_stat")
            fail_info = detail.get("failInfo") or {}
            if stat in (1, 2):
                return stat, fail_info
        except (ApiError, requests.RequestException) as exc:
            print(f"    查询向量化状态出错，继续轮询：{exc}")
        time.sleep(3)
    return stat, fail_info


def wait_embedding_ready(doc_id, first_timeout=150, retry_timeout=90):
    """等到 embedding_stat == 1；失败(2)先补救一次重新向量化，仍失败才放弃。"""
    stat, fail_info = _poll_embedding_stat(doc_id, first_timeout)
    if stat == 2:
        # 补救：触发一次重新向量化再等一轮，不要一检测到失败就放弃
        print(f"    向量化失败（failInfo={fail_info}），触发一次重新向量化重试 …")
        try:
            kb_request("POST", f"/llm-application/open/document/embedding/{doc_id}",
                       json_body={})
        except (ApiError, requests.RequestException) as exc:
            print(f"    重新向量化请求失败：{exc}")
        stat, fail_info = _poll_embedding_stat(doc_id, retry_timeout)
    if stat != 1:
        raise HostedKbUnavailable(
            f"文档向量化未就绪（embedding_stat={stat}, failInfo={fail_info}），"
            "此时检索端只会返回 200+空数组，等下去也不会有结果")


def cleanup_hosted_kb(kb_id, doc_id):
    if doc_id:
        try:
            kb_request("DELETE", f"/llm-application/open/document/{doc_id}")
            print(f"    已删除临时文档 {doc_id}")
        except (ApiError, requests.RequestException) as exc:
            print(f"    警告：删除临时文档失败：{exc}")
    if kb_id:
        try:
            kb_request("DELETE", f"/llm-application/open/knowledge/{kb_id}")
            print(f"    已删除临时知识库 {kb_id}")
        except (ApiError, requests.RequestException) as exc:
            print(f"    警告：删除临时知识库失败：{exc}")


def hosted_kb_flow(faq_bytes, question):
    """创建临时知识库 → 上传 → 等向量化就绪 → 检索；finally 里清理全部临时资源。"""
    kb_id, doc_id = None, None
    try:
        print("  [1/4] 创建临时知识库（Embedding-3）…")
        data = kb_request(
            "POST", "/llm-application/open/knowledge",
            json_body={
                "embedding_id": 11,
                "embedding_model": "Embedding-3",
                "name": f"faq-demo-{int(time.time())}",
                "description": "main.py 临时知识库，跑完即删",
            },
        ) or {}
        kb_id = data.get("id")
        if not kb_id:
            raise HostedKbUnavailable(f"创建知识库未返回 id：{data}")

        print(f"  [2/4] 上传 faq.txt 到 {kb_id}（knowledge_type=1 按标题段落切）…")
        data = kb_request(
            "POST", f"/llm-application/open/document/upload_document/{kb_id}",
            files={"files": ("faq.txt", faq_bytes, "text/plain")},
            data={"knowledge_type": "1"},
            timeout=120,
        ) or {}
        failed, success = data.get("failedInfos") or [], data.get("successInfos") or []
        if failed or not success:
            raise HostedKbUnavailable(f"文档上传失败：failedInfos={failed}")
        doc_id = success[0].get("documentId")
        print(f"        文档已上传：{doc_id}")

        print("  [3/4] 等待向量化完成（上传成功 ≠ 可检索，必须等到 embedding_stat==1）…")
        wait_embedding_ready(doc_id)

        print("  [4/4] 调用 /knowledge/retrieve 检索 …")
        hits = kb_request(
            "POST", "/llm-application/open/knowledge/retrieve",
            json_body={"query": question, "knowledge_ids": [kb_id], "top_k": 5},
        ) or []
        if not hits:
            # 200+空数组与"确实没有相关内容"无法区分；本任务的 FAQ 明确包含该主题，
            # 空召回视作此路不通，交给调用方降级
            raise HostedKbUnavailable("检索返回空数组（向量化已就绪但无召回）")
        return [
            {
                "text": h.get("text", ""),
                "score": h.get("score"),
                "source": (h.get("metadata") or {}).get("doc_name", "托管知识库切片"),
            }
            for h in hits
        ]
    finally:
        if kb_id or doc_id:
            print("  清理托管知识库临时资源 …")
            cleanup_hosted_kb(kb_id, doc_id)


# ------------------------------------------------- 降级方案：embeddings + rerank 自建检索

def split_chunks(text):
    """按空行切块（FAQ 常见排版），超长块再按行累计切成不超过 CHUNK_MAX_LEN 的段。"""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks = []
    for block in blocks:
        if len(block) <= CHUNK_MAX_LEN:
            chunks.append(block)
            continue
        current = ""
        for line in block.splitlines():
            if current and len(current) + len(line) + 1 > CHUNK_MAX_LEN:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)
    return chunks


def _embed_batched(model, dimensions, texts):
    vectors = [None] * len(texts)
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        payload = {"model": model, "input": batch}
        if dimensions:
            payload["dimensions"] = dimensions
        body = paas_post("/paas/v4/embeddings", payload)
        for item in body.get("data", []):
            vectors[start + item["index"]] = item["embedding"]  # 按 index 对齐
    if any(v is None for v in vectors):
        raise ApiError("/paas/v4/embeddings", "incomplete", "返回向量数量与输入不一致")
    return vectors


def embed_texts(texts):
    """embedding-3 失败时退回 embedding-2（查询与文档同一函数生成，向量空间必然一致）。"""
    try:
        return _embed_batched("embedding-3", 1024, texts)
    except ApiError as exc:
        print(f"    embedding-3 调用失败（{exc}），改用 embedding-2 重试 …")
        return _embed_batched("embedding-2", None, texts)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def local_rag_flow(text, question):
    """自建检索：本地切块 → embeddings 向量召回 top10 → rerank 精排 top5。

    不在服务端创建任何知识库/文档，因此无需清理。
    """
    chunks = split_chunks(text)
    if not chunks:
        raise RuntimeError("faq.txt 切块后为空，无法检索")

    print(f"  [1/3] 向量化：1 条查询 + {len(chunks)} 个切块 …")
    vectors = embed_texts([question] + chunks)
    query_vec = vectors[0]
    # 向量召回 top10
    recall = sorted(
        ((cosine(query_vec, vec), idx) for idx, vec in enumerate(vectors[1:])),
        key=lambda t: t[0], reverse=True,
    )[:10]

    print("  [2/3] rerank 精排（return_documents=true 以带回原文）…")
    try:
        results = paas_post(
            "/paas/v4/rerank",
            {
                "model": "rerank",
                "query": question,
                "documents": [chunks[idx] for _, idx in recall],
                "top_n": 5,
                "return_documents": True,
            },
        ).get("results", [])
        # results 只带 index 和分数，用 index 映射回自己的切块拿原文
        hits = [
            {
                "text": chunks[recall[r["index"]][1]],
                "score": r.get("relevance_score"),
                "source": f"faq.txt 切块 #{recall[r['index']][1] + 1}（向量召回+rerank 精排）",
            }
            for r in results
            if r.get("index") is not None and 0 <= r["index"] < len(recall)
        ]
        if hits:
            return hits, "embeddings 向量召回 + rerank 精排（自建检索）"
        print("    rerank 未返回可用结果，退化为纯向量排序输出 …")
    except ApiError as exc:
        print(f"    rerank 调用失败（{exc}），退化为纯向量排序输出 …")

    print("  [3/3] 按向量相似度排序输出 top5 …")
    return (
        [
            {"text": chunks[idx], "score": score,
             "source": f"faq.txt 切块 #{idx + 1}（向量召回）"}
            for score, idx in recall[:5]
        ],
        "embeddings 向量召回（rerank 不可用，纯向量排序）",
    )


# ---------------------------------------------------------------- 装配与输出

def read_faq_text():
    raw = FAQ_PATH.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def print_hits(route, hits):
    line = "=" * 64
    print(f"\n{line}\n检索到的原文片段\n问题：{QUESTION}\n路线：{route}\n{line}")
    for rank, hit in enumerate(hits, 1):
        score = hit.get("score")
        score_text = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
        print(f"[{rank}] 来源：{hit['source']}｜相似度：{score_text}")
        print(hit["text"])
        print("-" * 64)


def main():
    if not API_KEY:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。")
        return 1
    if not FAQ_PATH.is_file():
        print(f"错误：找不到 {FAQ_PATH}（请把 faq.txt 放在 main.py 同目录）。")
        return 1
    text = read_faq_text()
    if not text or not text.strip():
        print(f"错误：{FAQ_PATH} 为空或编码无法识别（支持 UTF-8 / GBK）。")
        return 1

    hits, route = [], ""
    print("[主路] 智谱托管知识库：创建 → 上传 faq.txt → 向量化 → 检索")
    try:
        hits = hosted_kb_flow(FAQ_PATH.read_bytes(), QUESTION)
        route = "智谱托管知识库 /llm-application/open/knowledge/retrieve"
    except (HostedKbUnavailable, ApiError, requests.RequestException) as exc:
        print(f"托管知识库这条路走不通：{exc}")
        print("\n[降级] 改用自建检索：/paas/v4/embeddings 召回 + /paas/v4/rerank 精排"
              "（本地切块检索，不在服务端创建资源，无需清理）")
        try:
            hits, detail = local_rag_flow(text, QUESTION)
            route = detail
        except (ApiError, requests.RequestException, RuntimeError) as exc:
            print(f"错误：自建检索也失败了：{exc}")
            return 1

    if not hits:
        print("错误：托管知识库与自建检索两条路都没有取回内容。")
        return 1

    print_hits(route, hits)
    print(f"✅ 检索成功，路线：{route}。"
          "托管知识库的临时文档/知识库已删除；自建方案无服务端资源。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
