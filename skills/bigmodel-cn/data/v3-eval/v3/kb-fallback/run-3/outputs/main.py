# -*- coding: utf-8 -*-
"""
把同目录 faq.txt 灌进智谱托管知识库并检索「退换货政策的有效期是多久」，
打印检索到的原文片段。

两条路径，自动降级：
  路径 A：托管知识库（/llm-application/open/*）
          创建知识库 -> 上传 faq.txt -> 轮询 embedding_stat 直到向量化就绪 -> 检索。
          已知的坑（实测验证过）：
            * 这一族接口出错时 HTTP 仍是 200，真实结果在 body["code"]，必须判 code；
            * 上传成功 != 可检索，向量化在后台异步跑，失败时检索端只回空数组，
              所以必须轮询 GET /document/{id} 的 embedding_stat（0 处理中 / 1 就绪 / 2 失败）。
  路径 B：自建检索（/paas/v4/embeddings + /paas/v4/rerank）
          路径 A 任何一步走不通（接口报错 / 向量化失败 / 检索为空）时自动降级：
          本地把 faq.txt 按行切块 -> embedding-3 向量化 -> 余弦召回 top32 -> rerank 精排 top5。
          无任何服务端残留资源，不需要清理。

无论走哪条路，最后都清理临时资源（删除临时知识库），并打印检索到的原文片段。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests + 标准库。
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://open.bigmodel.cn/api"
QUERY = "退换货政策的有效期是多久"
EMBED_MODEL = "embedding-3"
EMBED_DIMS = 1024          # 查询与文档必须用同一 model + dimensions，向量空间才一致
EMBED_BATCH = 64           # embedding-3 的 input 数组单次最多 64 条
RERANK_CANDIDATES = 32     # rerank 的 documents 上限 128 条，召回 32 条足够
TOP_K = 5

# 轮询向量化：每 5 秒查一次，最多等 180 秒；失败后触发一次重新向量化再等 60 秒
POLL_INTERVAL = 5
POLL_TIMEOUT = 180
REEMBED_TIMEOUT = 60


class KbError(Exception):
    """路径 A（托管知识库）中任何一步失败，用于触发降级到路径 B。"""


# ---------------------------------------------------------------- 通用请求 --

def _request(method, url, *, params=None, json_body=None, files=None, data=None,
             timeout=90, retries=3):
    """带重试的 requests 封装；返回解析后的 JSON（解析失败给出可读报错）。"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(
                method, url, headers=headers, params=params,
                json=json_body, files=files, data=data, timeout=timeout,
            )
            # /paas/v4/* 出错会返回真实的 4xx/5xx；5xx 重试，4xx 直接抛
            if resp.status_code >= 500 and attempt < retries:
                last_err = f"HTTP {resp.status_code}"
                time.sleep(2 * attempt)
                continue
            try:
                return resp.status_code, resp.json()
            except ValueError:
                raise KbError(f"{url} 返回了非 JSON 内容（HTTP {resp.status_code}）："
                             f"{resp.text[:200]!r}")
        except requests.RequestException as exc:
            last_err = str(exc)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise KbError(f"请求 {url} 连续失败：{last_err}")


def llm_app_call(method, path, **kwargs):
    """/llm-application/open/* 族：出错时 HTTP 依然是 200，必须判 body["code"]。"""
    status, body = _request(method, BASE + path, **kwargs)
    if not isinstance(body, dict) or body.get("code") != 200:
        raise KbError(f"{path} 失败：HTTP {status}, body={json.dumps(body, ensure_ascii=False)[:300]}")
    return body


def paas_call(path, payload, timeout=90):
    """/paas/v4/* 族（embeddings/rerank）：4xx/5xx 是真实错误码。"""
    status, body = _request("POST", BASE + path, json_body=payload, timeout=timeout)
    if status != 200 or "error" in body:
        raise KbError(f"{path} 失败：HTTP {status}, body={json.dumps(body, ensure_ascii=False)[:300]}")
    return body


# ---------------------------------------------------------------- 路径 A ----

def create_kb():
    resp = llm_app_call("POST", "/llm-application/open/knowledge", json_body={
        "embedding_id": 11,            # Embedding-3
        "embedding_model": "Embedding-3",
        "name": f"tmp-faq-kb-{int(time.time())}",
        "description": "临时测试知识库，脚本结束时会删除",
    })
    return resp["data"]["id"]


def upload_doc(kb_id, faq_path):
    status, body = _request(
        "POST", f"{BASE}/llm-application/open/document/upload_document/{kb_id}",
        files={"files": (faq_path.name, faq_path.read_bytes(), "text/plain")},
        data={"knowledge_type": 1},   # 按标题段落切，txt 支持该模式
        timeout=120,
    )
    if not isinstance(body, dict) or body.get("code") != 200:
        raise KbError(f"上传文档失败：HTTP {status}, body={json.dumps(body, ensure_ascii=False)[:300]}")
    failed = body.get("data", {}).get("failedInfos") or []
    if failed:
        raise KbError(f"上传文档失败：{failed}")
    infos = body.get("data", {}).get("successInfos") or []
    if not infos:
        raise KbError("上传返回 code=200 但没有 documentId")
    return infos[0]["documentId"]


def wait_embedding(doc_id, timeout):
    """轮询文档详情直到向量化就绪。返回 True/False，不在这里抛错。
    失败（stat==2）时触发一次重新向量化再等一轮，只重试这一次。"""
    reembedded = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, body = _request("GET", f"{BASE}/llm-application/open/document/{doc_id}")
        stat = body.get("data", {}).get("embedding_stat")
        if stat == 1:
            return True
        if stat == 2:
            fail = body.get("data", {}).get("failInfo") or {}
            if reembedded:
                print(f"    重新向量化后仍失败（{fail.get('embedding_code')} "
                      f"{fail.get('embedding_msg')}）")
                return False
            print(f"    向量化失败（{fail.get('embedding_code')} "
                  f"{fail.get('embedding_msg')}），尝试重新向量化一次")
            llm_app_call("POST", f"/llm-application/open/document/embedding/{doc_id}",
                         json_body={})
            reembedded = True
            deadline = time.time() + REEMBED_TIMEOUT
            continue
        time.sleep(POLL_INTERVAL)
    return False


def kb_retrieve(kb_id):
    payload = {
        "query": QUERY,
        "knowledge_ids": [kb_id],
        "top_k": TOP_K,
        "recall_method": "mixed",
        "rerank_status": 1,
        "rerank_model": "rerank-pro",
    }
    hits = []
    for attempt in range(2):  # 就绪后偶发索引延迟，空结果时隔 5 秒再试一次
        body = llm_app_call("POST", "/llm-application/open/knowledge/retrieve", json_body=payload)
        hits = body.get("data") or []
        if hits:
            return hits
        if attempt == 0:
            time.sleep(POLL_INTERVAL)
    # 空数组与"确实没有相关内容"无法区分，这里按"这条路走不通"降级
    raise KbError("检索持续返回空结果（向量化可能实际未成功）")


def try_managed_kb(faq_path):
    """路径 A 全流程。成功返回命中列表；失败抛 KbError。临时知识库的清理在 main 的 finally 里做。"""
    kb_id = None
    doc_id = None
    try:
        print("[路径 A] 使用托管知识库 …")
        kb_id = create_kb()
        print(f"    知识库已创建：{kb_id}")
        doc_id = upload_doc(kb_id, faq_path)
        print(f"    文档已上传：{doc_id}，等待向量化 …")
        if not wait_embedding(doc_id, POLL_TIMEOUT):
            raise KbError("等待向量化超时")
        print("    向量化就绪，开始检索")
        return kb_retrieve(kb_id)
    finally:
        cleanup(kb_id, doc_id)


def cleanup(kb_id, doc_id):
    """清理临时资源：删临时知识库（含库内文档）；删库失败时至少把文档删掉。"""
    if not kb_id:
        return
    try:
        llm_app_call("DELETE", f"/llm-application/open/knowledge/{kb_id}")
        print(f"[清理] 临时知识库 {kb_id} 已删除")
        return
    except KbError as exc:
        print(f"[清理] 删除知识库失败：{exc}")
    if doc_id:
        try:
            llm_app_call("DELETE", f"/llm-application/open/document/{doc_id}")
            print(f"[清理] 文档 {doc_id} 已删除（知识库 {kb_id} 删除失败，请手动清理）")
        except KbError as exc:
            print(f"[清理] 删除文档也失败，请手动清理知识库 {kb_id} / 文档 {doc_id}：{exc}")


# ---------------------------------------------------------------- 路径 B ----

def chunk_faq(text):
    """按行切块（本文件一行一条 QA）；超长行再硬切成 ~400 字的段。"""
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        while len(line) > 800:
            chunks.append(line[:800])
            line = line[800:]
        chunks.append(line)
    return chunks


def embed(texts):
    """批量向量化，按返回的 index 对齐（不假设返回顺序）。"""
    vectors = [None] * len(texts)
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        body = paas_call("/paas/v4/embeddings", {
            "model": EMBED_MODEL, "input": batch, "dimensions": EMBED_DIMS,
        })
        for item in body["data"]:
            vectors[start + item["index"]] = item["embedding"]
    if any(v is None for v in vectors):
        raise KbError("embeddings 返回条数与输入不一致")
    return vectors


def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def fallback_local_rag(faq_path):
    """路径 B：embedding 召回 + rerank 精排的自建检索，不依赖托管知识库。"""
    print("[路径 B] 降级为 embeddings + rerank 自建检索 …")
    chunks = chunk_faq(faq_path.read_text(encoding="utf-8"))
    print(f"    共切出 {len(chunks)} 个文本块，开始向量化")
    doc_vecs = embed(chunks)
    query_vec = embed([QUERY])[0]

    scored = sorted(
        ((cosine(query_vec, v), i) for i, v in enumerate(doc_vecs)),
        reverse=True,
    )
    recalled = [i for _, i in scored[:RERANK_CANDIDATES]]
    print(f"    余弦召回 top{len(recalled)} 完成，进入 rerank 精排")

    try:
        body = paas_call("/paas/v4/rerank", {
            "model": "rerank",
            "query": QUERY,
            "documents": [chunks[i] for i in recalled],
            "top_n": TOP_K,
            "return_documents": True,   # results 默认只有 index+分数，要原文必须显式打开
        })
        # 以我们自己的 chunks[index] 为原文来源（ authoritative），不依赖回传的 document 字段
        hits = [{
            "score": r.get("relevance_score"),
            "text": chunks[recalled[r["index"]]],
            "source": "embedding召回+rerank精排",
        } for r in body["results"][:TOP_K]]
        if hits:
            return hits
        print("    rerank 未返回结果，退回纯向量召回排序")
    except KbError as exc:
        print(f"    rerank 失败（{exc}），退回纯向量召回排序")

    return [{
        "score": round(s, 4),
        "text": chunks[i],
        "source": "embedding余弦召回",
    } for s, i in scored[:TOP_K]]


# ---------------------------------------------------------------- 主流程 ---

def print_hits(hits):
    print("\n" + "=" * 62)
    print(f"检索问题：{QUERY}")
    print(f"检索到 {len(hits)} 条原文片段：")
    print("=" * 62)
    for rank, hit in enumerate(hits, 1):
        score = hit.get("score")
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "-"
        text = hit["text"].strip()
        print(f"\n[{rank}] score={score_s}  来源={hit.get('source', '托管知识库')}")
        print(f"    {text}")
    print()


def main():
    global API_KEY
    API_KEY = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not API_KEY:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    if not faq_path.is_file():
        sys.exit(f"找不到 {faq_path}，请把 faq.txt 放在 main.py 同目录")

    hits = None
    try:
        hits = try_managed_kb(faq_path)
        for h in hits:
            h.setdefault("source", h.get("metadata", {}).get("doc_name", "托管知识库"))
    except KbError as exc:
        print(f"[路径 A] 走不通：{exc}")
        print("自动降级到自建检索（仍然会真实检索并打印原文片段）")
        hits = fallback_local_rag(faq_path)

    if not hits:
        sys.exit("两条路径都没有检索到内容，请检查 API Key 权限与 faq.txt 内容")

    print_hits(hits)
    print("[完成] 检索结果已打印；路径 B 不产生服务端资源，无需额外清理")


if __name__ == "__main__":
    main()
