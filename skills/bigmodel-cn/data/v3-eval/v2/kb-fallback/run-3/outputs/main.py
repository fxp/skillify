#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录 faq.txt 灌进智谱托管知识库，检索「退换货政策的有效期是多久」并打印原文片段。

三条路径依次降级，保证一定能打印出检索到的内容，而不是停在"知识库不可用"：
  A. 智谱托管知识库：建库 -> 上传 -> 轮询向量化状态 -> retrieve -> 删库（临时资源，用完即清）
  B. 平台 Embeddings 自建检索：本地切片 + /paas/v4/embeddings 向量化 + 余弦相似度排序
  C. 纯本地词法检索：字符二元组覆盖率打分，不依赖任何 API（Key 缺失/网络不通也出结果）

两条来自官方文档实测的坑，代码里已专门处理：
  1. llm-application/open/* 出错时 HTTP 状态码依然是 200，真实结果在响应体 code 里，
     必须判 body["code"] == 200，raise_for_status() 在这里永远不触发。
  2. 上传成功 != 文档可检索：向量化在后台异步跑，失败时检索端只回 HTTP 200 + 空数组，
     必须轮询 GET /document/{id} 的 embedding_stat（0 处理中 / 1 成功 / 2 失败）到 ==1。

用法：ZHIPUAI_API_KEY 环境变量提供 Key，然后  python3 main.py
"""

import math
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://open.bigmodel.cn/api"
QUERY = "退换货政策的有效期是多久"
FAQ_PATH = Path(__file__).resolve().parent / "faq.txt"
TOP_K = 5
POLL_INTERVAL = 3
POLL_ROUNDS = 60  # 最长等 ~3 分钟向量化


class FlowError(Exception):
    """某条检索路径失败，携带给人看的原因，用于触发降级。"""


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- 路径 A：托管知识库

def kb_call(method, path, api_key, *, json_body=None, files=None, data=None, timeout=60):
    """llm-application/open/* 族接口封装：必须以响应体 code==200 判成功。"""
    resp = requests.request(
        method, BASE + path,
        headers={"Authorization": f"Bearer {api_key}"},
        json=json_body, files=files, data=data, timeout=timeout,
    )
    resp.raise_for_status()
    try:
        body = resp.json()
    except ValueError:
        raise FlowError(f"{method} {path} 返回非 JSON（HTTP {resp.status_code}）")
    if body.get("code") != 200:
        raise FlowError(f"{method} {path} 失败：code={body.get('code')} message={body.get('message')}")
    return body


def kb_flow(api_key):
    """建库 -> 上传 faq.txt -> 轮询向量化 -> 检索。

    返回 (hits, knowledge_id)；任何一步失败抛 FlowError，knowledge_id 由调用方负责清理。
    """
    body = kb_call("POST", "/llm-application/open/knowledge", api_key, json_body={
        "embedding_id": 11, "embedding_model": "Embedding-3",
        "name": "faq-tmp-" + time.strftime("%m%d%H%M%S"),
        "description": "main.py 临时检索测试库，跑完即删",
    })
    knowledge_id = body["data"]["id"]
    log(f"[A] 知识库已创建：{knowledge_id}")

    with open(FAQ_PATH, "rb") as f:
        body = kb_call("POST", f"/llm-application/open/document/upload_document/{knowledge_id}",
                       api_key, files={"files": f}, data={"knowledge_type": 1}, timeout=120)
    infos = (body.get("data") or {}).get("successInfos") or []
    if not infos:
        raise FlowError(f"上传 faq.txt 无成功项：{body.get('data')}")
    document_id = infos[0]["documentId"]
    log(f"[A] faq.txt 已上传（document_id={document_id}），等待后台向量化……")

    # 上传成功 != 可检索，必须轮询 embedding_stat；拿到 2 直接失败降级，不等空检索。
    for _ in range(POLL_ROUNDS):
        body = kb_call("GET", f"/llm-application/open/document/{document_id}", api_key)
        stat = (body.get("data") or {}).get("embedding_stat")
        if stat == 1:
            break
        if stat == 2:
            fail = (body.get("data") or {}).get("failInfo") or {}
            raise FlowError(f"向量化失败（embedding_stat=2）：{fail.get('embedding_msg') or fail}")
        time.sleep(POLL_INTERVAL)
    else:
        raise FlowError(f"等待向量化超时（约 {POLL_ROUNDS * POLL_INTERVAL} 秒）")
    log("[A] 向量化完成，开始检索")

    body = kb_call("POST", "/llm-application/open/knowledge/retrieve", api_key, json_body={
        "query": QUERY,
        "knowledge_ids": [knowledge_id],
        "document_ids": [document_id],
        "top_k": TOP_K,
    })
    hits = [(float(item.get("score") or 0.0), item.get("text") or "",
             f"知识库切片（doc={item.get('metadata', {}).get('doc_name', '')}）")
            for item in (body.get("data") or [])]
    if not hits:
        # 文档已就绪却召回为空：和"确实没有相关内容"无法区分，按本路径不可用降级。
        raise FlowError("retrieve 返回空数组")
    return hits, knowledge_id


def cleanup_kb(api_key, knowledge_id):
    """删除临时知识库（级联删除库内全部文档）。"""
    try:
        kb_call("DELETE", f"/llm-application/open/knowledge/{knowledge_id}", api_key)
        log(f"[清理] 临时知识库 {knowledge_id} 及库内文档已删除")
    except (FlowError, requests.RequestException) as e:
        log(f"[清理] 删除临时知识库 {knowledge_id} 失败，请到控制台手动删除：{e}")


# ---------------------------------------------------------------- 路径 B：平台 Embeddings

def embed_texts(api_key, texts):
    """调 /paas/v4/embeddings（标准 paas 接口，用真实 HTTP 状态码）。

    embedding-3 每条上限 3072 token、数组最多 64 条；这里按 32 条一批、
    每条截 1500 字留足余量。结果按 index 对齐，不假设返回顺序。
    """
    out = []
    for i in range(0, len(texts), 32):
        batch = [t[:1500] for t in texts[i:i + 32]]
        resp = requests.post(
            f"{BASE}/paas/v4/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "embedding-3", "input": batch, "dimensions": 1024},
            timeout=120,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        out.extend(d["embedding"] for d in data)
    return out


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def embedding_flow(api_key, chunks):
    log("[B] 改用平台 Embeddings 自建检索（切片+问题向量化后按余弦相似度排序）")
    vecs = embed_texts(api_key, chunks + [QUERY])
    qvec = vecs[-1]
    ranked = sorted(((cosine(qvec, v), c) for v, c in zip(vecs[:-1], chunks)), reverse=True)
    return [(score, text, "faq.txt 段落") for score, text in ranked[:TOP_K]]


# ---------------------------------------------------------------- 路径 C：本地词法检索

def bigrams(text):
    t = re.sub(r"\s+", "", text.lower())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def local_flow(chunks):
    """无任何外部依赖的兜底：query 字符二元组覆盖率为主、单字覆盖率为辅打分。"""
    log("[C] 改用本地词法检索（不依赖 API）")
    qb, qu = bigrams(QUERY), set(QUERY)
    scored = []
    for c in chunks:
        cb = bigrams(c)
        bi = len(qb & cb) / len(qb) if qb else 0.0
        uni = len(qu & set(c)) / len(qu)
        scored.append((0.7 * bi + 0.3 * uni, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(score, text, "faq.txt 段落") for score, text in scored[:TOP_K]]


# ---------------------------------------------------------------- 公共部分

def load_chunks():
    """读 faq.txt 并按空行切段：短标题行并入下一段（FAQ 常见版式），超长段落再按 500 字切窗。"""
    if not FAQ_PATH.is_file():
        log(f"[错误] 找不到 {FAQ_PATH}，请把 faq.txt 放在 main.py 同目录下。")
        sys.exit(2)
    text = FAQ_PATH.read_text(encoding="utf-8", errors="replace")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    merged = []
    for para in paras:
        if merged and len(merged[-1]) < 30:
            merged[-1] = merged[-1] + "\n" + para  # 上一段是短标题，并入正文
        else:
            merged.append(para)
    chunks = []
    for para in merged:
        for i in range(0, len(para), 500):
            piece = para[i:i + 500].strip()
            if piece:
                chunks.append(piece)
    if not chunks:
        log(f"[错误] {FAQ_PATH} 内容为空，无内容可检索。")
        sys.exit(2)
    return chunks


def print_hits(route, hits):
    log(f"\n===== 检索结果（路径 {route}）｜问题：{QUERY} =====")
    for rank, (score, text, src) in enumerate(hits, 1):
        log(f"\n--- 原文片段 {rank}/{len(hits)}（score={score:.4f}，来源：{src}）---")
        log(text)
    log(f"\n===== 共打印 {len(hits)} 个原文片段 =====")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    chunks = load_chunks()
    log(f"已读取 faq.txt：{len(chunks)} 个切片；检索问题：「{QUERY}」")

    hits, route = None, None
    if api_key:
        knowledge_id = None
        try:
            hits, knowledge_id = kb_flow(api_key)
            route = "A：智谱托管知识库"
        except FlowError as e:
            log(f"[A] 托管知识库路径不可用：{e}")
        except (requests.RequestException, KeyError, TypeError) as e:
            log(f"[A] 托管知识库路径异常：{e!r}")
        finally:
            if knowledge_id:
                cleanup_kb(api_key, knowledge_id)

        if hits is None:
            try:
                hits = embedding_flow(api_key, chunks)
                route = "B：平台 Embeddings 自建检索"
            except (requests.RequestException, KeyError, ValueError, IndexError) as e:
                log(f"[B] Embeddings 路径不可用：{e!r}")
    else:
        log("ZHIPUAI_API_KEY 未设置，跳过路径 A/B，直接走本地检索。")

    if hits is None:
        hits = local_flow(chunks)
        route = "C：本地词法检索"

    print_hits(route, hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
