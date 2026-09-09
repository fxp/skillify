#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录 faq.txt 灌进智谱（bigmodel.cn）并检索「退换货政策的有效期是多久」，
把检索到的**原文片段**打印出来。

两条通道，自动降级：
  方案一（首选）：托管知识库
      创建知识库 → 上传 faq.txt → 轮询文档向量化状态 → /knowledge/retrieve 检索
  方案二（降级）：托管知识库任何一步走不通时，改用标准 /paas/v4/embeddings 接口
      自建向量检索：本地切分 faq.txt → 向量化 → 余弦相似度召回 → rerank 精排（尽力而为）

针对智谱接口的两个实测陷阱做了防御：
  1) /llm-application/open/* 出错时 HTTP 状态码仍是 200，真实结果在响应体 code 里
     —— 所以每一步都判 body["code"] == 200，而不是 raise_for_status()。
  2) 上传成功 ≠ 文档可检索：向量化在后台异步跑，失败时检索端永远返回 200 + 空数组
     —— 所以上传后轮询 GET /document/{id} 的 embedding_stat（0 处理中 / 1 就绪 / 2 失败），
     等到 1 才检索；得到 2 直接降级；检索结果为空也视为走不通并降级。

无论走哪条通道，结束时都清理临时资源：托管通道删除本次创建的知识库（连同文档）；
自建通道不在服务端创建任何资源，无需清理。

依赖：仅 requests + 标准库。运行：
    ZHIPUAI_API_KEY=你的key python3 main.py
"""

import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
KB_BASE = f"{BASE_URL}/llm-application/open"   # 托管知识库（HTTP 恒 200，判 body.code）
PAAS_BASE = f"{BASE_URL}/paas/v4"              # 标准 API（HTTP 状态码即真实结果）

QUESTION = "退换货政策的有效期是多久"
FAQ_PATH = Path(__file__).resolve().parent / "faq.txt"

EMBED_MODEL = "embedding-3"   # 与托管知识库创建时绑定的 embedding_id=11（Embedding-3）对应
EMBED_DIM = 1024             # 向量维度；查询必须与切片用同一 model+dimensions 组合
EMBED_BATCH = 32             # embedding-3 单次数组上限 64 条，留余量
RERANK_MODEL = "rerank"

TOP_K = 5                    # 最终打印的原文片段数
EMBED_WAIT_TIMEOUT = 180     # 等托管知识库向量化的上限（秒）
EMBED_POLL_INTERVAL = 5

API_KEY = os.environ.get("ZHIPUAI_API_KEY", "").strip()
SESSION = requests.Session()
SESSION.headers["Authorization"] = f"Bearer {API_KEY}"


class KbStepError(RuntimeError):
    """托管知识库某一步走不通（用于触发降级）。"""


# ---------------------------------------------------------------- 托管知识库通道

def kb_request(method, path, **kwargs):
    """调用 /llm-application/open/*：出错时 HTTP 仍是 200，必须判 body.code。"""
    resp = SESSION.request(method, f"{KB_BASE}{path}", timeout=60, **kwargs)
    resp.raise_for_status()
    try:
        body = resp.json()
    except ValueError:
        raise KbStepError(f"{method} {path} 返回非 JSON: {resp.text[:200]}")
    if body.get("code") != 200:
        raise KbStepError(
            f"{method} {path} 失败: code={body.get('code')} message={body.get('message')}")
    return body


def wait_embedding_ready(document_id):
    """轮询文档详情直到向量化就绪。embedding_stat: 0=处理中 1=成功 2=失败。"""
    deadline = time.time() + EMBED_WAIT_TIMEOUT
    consecutive_errors = 0
    while time.time() < deadline:
        try:
            body = kb_request("GET", f"/document/{document_id}")
            consecutive_errors = 0
            doc = body.get("data") or {}
            stat = doc.get("embedding_stat")
            if stat == 1:
                print("[托管知识库] 向量化就绪 (embedding_stat=1)")
                return
            if stat == 2:
                fail_info = doc.get("failInfo") or {}
                raise KbStepError(
                    "文档向量化失败 (embedding_stat=2): "
                    f"{fail_info.get('embedding_msg') or '未知原因'}")
            print(f"[托管知识库] 向量化处理中 (embedding_stat={stat})，"
                  f"{EMBED_POLL_INTERVAL}s 后再查…")
        except KbStepError:
            raise
        except Exception as exc:  # 轮询期的偶发网络错误容忍几次
            consecutive_errors += 1
            if consecutive_errors >= 3:
                raise KbStepError(f"查询文档状态连续失败: {exc}")
            print(f"[托管知识库] 查询文档状态出错（{exc}），重试…")
        time.sleep(EMBED_POLL_INTERVAL)
    raise KbStepError(f"等待向量化超时（>{EMBED_WAIT_TIMEOUT}s）")


def run_managed_kb(ctx):
    """创建知识库 → 上传 faq.txt → 等向量化 → 检索。ctx 记录待清理的资源 ID。"""
    kb_name = f"faq-retrieval-demo-{datetime.now():%Y%m%d%H%M%S}"
    body = kb_request("POST", "/knowledge", json={
        "embedding_id": 11,  # Embedding-3
        "name": kb_name,
        "description": "由 main.py 创建的临时知识库，脚本结束时自动删除",
    })
    knowledge_id = (body.get("data") or {}).get("id")
    if not knowledge_id:
        raise KbStepError(f"创建知识库成功但未返回 id: {body}")
    ctx["knowledge_id"] = knowledge_id
    print(f"[托管知识库] 创建成功: {knowledge_id} ({kb_name})")

    with open(FAQ_PATH, "rb") as fh:
        body = kb_request(
            "POST",
            f"/document/upload_document/{knowledge_id}",
            files={"files": (FAQ_PATH.name, fh, "text/plain")},
            data={"knowledge_type": 1},  # 1=按标题段落切，支持 txt
        )
    data = body.get("data") or {}
    success = data.get("successInfos") or []
    failed = data.get("failedInfos") or []
    if not success:
        raise KbStepError(f"上传失败: {failed or 'successInfos 为空'}")
    document_id = success[0].get("documentId")
    ctx["document_ids"].append(document_id)
    print(f"[托管知识库] 上传成功: {document_id} ({FAQ_PATH.name})")

    wait_embedding_ready(document_id)

    body = kb_request("POST", "/knowledge/retrieve", json={
        "query": QUESTION,
        "knowledge_ids": [knowledge_id],
        "top_k": TOP_K,
        "recall_method": "mixed",
    })
    hits = body.get("data") or []
    if not hits:
        # 实测陷阱：向量化失败时检索端返回 200+空数组，与"没有相关内容"无法区分。
        # faq.txt 里确实有退换货政策，检索为空只能说明这条流水线不可用 → 降级。
        raise KbStepError("检索返回空结果（向量化可能失败或未完成）")
    print(f"[托管知识库] 检索到 {len(hits)} 条片段")
    return [{
        "text": h.get("text", ""),
        "score": h.get("score"),
        "doc": (h.get("metadata") or {}).get("doc_name") or "托管知识库",
    } for h in hits]


def cleanup_managed_kb(ctx):
    """删除本次创建的知识库（连同库内全部文档）；删库失败再逐个删文档兜底。"""
    knowledge_id = ctx.get("knowledge_id")
    if not knowledge_id:
        return
    try:
        kb_request("DELETE", f"/knowledge/{knowledge_id}")
        print(f"[清理] 已删除知识库 {knowledge_id}（含全部文档）")
        return
    except Exception as exc:
        print(f"[清理] 删除知识库失败（{exc}），尝试逐个删除文档…")
    for doc_id in ctx.get("document_ids") or []:
        try:
            kb_request("DELETE", f"/document/{doc_id}")
            print(f"[清理] 已删除文档 {doc_id}")
        except Exception as exc:
            print(f"[清理] 删除文档 {doc_id} 失败: {exc}")


# ------------------------------------------------------- 降级通道：自建向量检索

def paas_post(path, payload, timeout=120):
    """调用标准 /paas/v4/*：HTTP 状态码即真实结果，出错时带上响应体细节。"""
    resp = SESSION.post(f"{PAAS_BASE}{path}", json=payload, timeout=timeout)
    if resp.status_code != 200:
        detail = resp.text[:200]
        try:
            err = resp.json().get("error") or {}
            detail = f"code={err.get('code')} message={err.get('message')}"
        except ValueError:
            pass
        raise RuntimeError(f"POST {path} 失败 HTTP {resp.status_code}: {detail}")
    return resp.json()


def chunk_faq(text, max_len=1200):
    """按空行切成段落（FAQ 通常是"一问一答一块"）；超长段落再按 max_len 硬切。"""
    chunks = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if len(block) <= max_len:
            chunks.append(block)
        else:
            chunks.extend(block[i:i + max_len] for i in range(0, len(block), max_len))
    return chunks


def embed_texts(texts):
    """批量向量化。结果按返回的 index 对齐，不假设顺序。"""
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        body = paas_post("/embeddings", {
            "model": EMBED_MODEL,
            "input": batch,
            "dimensions": EMBED_DIM,
        })
        data = sorted(body.get("data") or [], key=lambda d: d.get("index", 0))
        if len(data) != len(batch):
            raise RuntimeError(
                f"embeddings 返回数量不符: 期望 {len(batch)} 实得 {len(data)}")
        vectors.extend(d["embedding"] for d in data)
    return vectors


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rerank_candidates(query, chunks, candidate_idx):
    """用 /paas/v4/rerank 精排。返回 [(chunk下标, relevance_score), ...] 按分数降序。"""
    body = paas_post("/rerank", {
        "model": RERANK_MODEL,
        "query": query,
        "documents": [chunks[i] for i in candidate_idx],
        "top_n": len(candidate_idx),
        "return_documents": False,
    }, timeout=60)
    return [(candidate_idx[r["index"]], r["relevance_score"])
            for r in body.get("results") or [] if r.get("index") is not None]


def run_local_retrieval():
    """自建检索：本地切分 → embeddings → 余弦召回 →（可选）rerank 精排。"""
    text = FAQ_PATH.read_text(encoding="utf-8-sig")  # utf-8-sig 兼容带 BOM 的文件
    chunks = chunk_faq(text)
    if not chunks:
        raise RuntimeError("faq.txt 切分后没有任何内容")
    print(f"[自建检索] faq.txt 切分为 {len(chunks)} 个片段，"
          f"调用 {EMBED_MODEL} 向量化（{EMBED_DIM} 维）…")

    chunk_vectors = embed_texts(chunks)
    query_vector = embed_texts([QUESTION])[0]

    scored = sorted(
        ((cosine(query_vector, v), i) for i, v in enumerate(chunk_vectors)),
        reverse=True,
    )

    # rerank 精排是增强项：调用失败不影响已有召回结果
    try:
        candidate_idx = [i for _, i in scored[:20]]
        reranked = rerank_candidates(QUESTION, chunks, candidate_idx)
        if reranked:
            reranked.sort(key=lambda t: t[1], reverse=True)
            done = {i for i, _ in reranked}
            rest = [(s, i) for s, i in scored if i not in done]
            scored = [(s, i) for i, s in reranked] + rest
            print("[自建检索] rerank 精排完成")
    except Exception as exc:
        print(f"[自建检索] rerank 不可用（{exc}），使用余弦相似度排序")

    return [{
        "text": chunks[i],
        "score": round(score, 4),
        "doc": "faq.txt",
    } for score, i in scored[:TOP_K]]


# ------------------------------------------------------------------------ 输出

def print_snippets(source, hits):
    print("\n" + "=" * 64)
    print(f"检索通道：{source}")
    print(f"问题：{QUESTION}")
    print(f"共检索到 {len(hits)} 条原文片段：")
    for rank, hit in enumerate(hits, 1):
        print(f"\n----- 片段 {rank}（score={hit['score']}，来源：{hit['doc']}）-----")
        print(hit["text"])
    print("\n" + "=" * 64)


def main():
    if not API_KEY:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1
    if not FAQ_PATH.exists():
        print(f"错误：找不到 {FAQ_PATH}，请把 faq.txt 放在脚本同目录", file=sys.stderr)
        return 1

    ctx = {"knowledge_id": None, "document_ids": []}
    exit_code = 1
    try:
        print("=" * 64)
        print(f"问题：{QUESTION}")
        print("=" * 64)

        print("\n>>> 方案一：智谱托管知识库")
        try:
            hits = run_managed_kb(ctx)
            source = "托管知识库 POST /llm-application/open/knowledge/retrieve"
        except Exception as exc:
            print(f"\n[托管知识库] 走不通：{exc}")
            print("\n>>> 方案二：自建向量检索（/paas/v4/embeddings + 余弦相似度 + rerank）")
            try:
                hits = run_local_retrieval()
                source = "自建 embedding 检索（POST /paas/v4/embeddings）"
            except Exception as exc2:
                print(f"\n[自建检索] 也失败了：{exc2}", file=sys.stderr)
                return 1

        print_snippets(source, hits)
        exit_code = 0
    finally:
        # 无论成功、失败还是降级，都清理托管通道创建的临时资源；
        # 自建通道没有在服务端创建任何资源，无需清理。
        cleanup_managed_kb(ctx)
        if not ctx.get("knowledge_id"):
            print("[清理] 自建通道未在服务端创建资源，无需清理")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
