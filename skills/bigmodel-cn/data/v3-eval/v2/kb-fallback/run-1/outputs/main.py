#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录 faq.txt 灌进智谱开放平台（bigmodel.cn）的托管知识库，
再用「退换货政策的有效期是多久」检索，并打印检索到的原文片段。

三级方案自动降级，保证一定打印出检索结果：
  方案一：托管知识库（创建 → 上传 → 轮询向量化 → /knowledge/retrieve）
  方案二：智谱 Embeddings API 自建向量检索（embedding-3 召回 + rerank 精排）
  方案三：本地字符 bigram 词法检索（零网络依赖，必然可用）

两个已知坑的处理（来自实测）：
  1) /llm-application/open/* 出错时 HTTP 仍是 200，真实结果在 body.code，必须判 code；
  2) 上传成功 ≠ 可检索：向量化是后台异步的，需轮询文档 embedding_stat
     （0=处理中 1=就绪 2=失败），失败时检索端只返回空数组、不报错。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import math
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://open.bigmodel.cn/api"
QUERY = "退换货政策的有效期是多久"
TOP_K = 5
EMB_MODEL = "embedding-3"
EMB_DIM = 1024
EMB_BATCH = 64          # embedding-3 单次 input 数组上限 64 条
TIMEOUT = 60            # 单个请求超时（秒）
POLL_INTERVAL = 3       # 轮询向量化状态的间隔（秒）
POLL_DEADLINE = 120     # 等待向量化完成的最长时间（秒）

API_KEY = os.environ.get("ZHIPUAI_API_KEY", "").strip()


def _find_faq():
    for cand in (Path(__file__).resolve().parent / "faq.txt", Path.cwd() / "faq.txt"):
        if cand.is_file():
            return cand
    return None


FAQ_PATH = _find_faq()


# ---------------------------------------------------------------- 通用工具

def code_ok(body):
    """知识库族接口任何情况都返回 HTTP 200，真实成败在 body.code（200 才算成功）。"""
    try:
        return body is not None and int(body.get("code")) == 200
    except (AttributeError, TypeError, ValueError):
        return False


def call_api(method, url, **kw):
    """发请求并解析 JSON。网络/网关层异常直接抛出，由各方案捕获后降级。"""
    resp = requests.request(
        method, url,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=TIMEOUT, **kw,
    )
    resp.raise_for_status()  # 知识库接口的业务错误不走这里，只拦网关级错误
    return resp.json()


def describe_exc(e):
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f"HTTP {e.response.status_code} {e.response.text[:200]}"
    return repr(e)


def load_faq_lines():
    text = FAQ_PATH.read_text(encoding="utf-8")
    return [(no, ln.strip()) for no, ln in enumerate(text.splitlines(), 1) if ln.strip()]


def print_results(source, hits):
    print(f"\n===== 检索到的原文片段（方案：{source}）=====")
    print(f"问题：{QUERY}")
    for i, h in enumerate(hits, 1):
        extras = []
        if h.get("line_no"):
            extras.append(f"faq.txt 第{h['line_no']}行")
        if h.get("doc_name"):
            extras.append(f"来源文档 {h['doc_name']}")
        tag = f"（{'，'.join(extras)}）" if extras else ""
        score = h.get("score")
        score_str = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
        print(f"[{i}] score={score_str}{tag}")
        print(f"    {h.get('text', '').strip()}")


# ---------------------------------------------------------------- 方案一：托管知识库

def retrieve_via_hosted_kb(res):
    """res 记录已创建的资源 id，供调用方在 finally 里清理。成功返回 (hits, None)。"""
    r = call_api("POST", f"{BASE}/llm-application/open/knowledge",
                 json={"embedding_id": 11,  # 11 = Embedding-3
                       "name": f"faq-tmp-{int(time.time())}",
                       "description": "main.py 临时知识库，脚本结束自动删除"})
    if not code_ok(r):
        return None, f"创建知识库失败 code={r.get('code')} message={r.get('message')}"
    res["kb_id"] = (r.get("data") or {}).get("id")
    if not res["kb_id"]:
        return None, f"创建知识库响应缺少 data.id：{str(r)[:200]}"
    print(f"  [1/4] 知识库已创建：{res['kb_id']}")

    with open(FAQ_PATH, "rb") as f:
        r = call_api("POST", f"{BASE}/llm-application/open/document/upload_document/{res['kb_id']}",
                     files={"files": (FAQ_PATH.name, f, "text/plain")},
                     # knowledge_type=5 自定义切分 + 换行分隔：一行一条 FAQ
                     data=[("knowledge_type", "5"), ("custom_separator", "\n"),
                           ("sentence_size", "300"), ("parse_image", "false")])
    if not code_ok(r):
        return None, f"上传文档失败 code={r.get('code')} message={r.get('message')}"
    infos = (r.get("data") or {}).get("successInfos") or []
    if not infos:
        return None, f"上传无成功项 failedInfos={(r.get('data') or {}).get('failedInfos')}"
    res["doc_id"] = infos[0].get("documentId")
    print(f"  [2/4] 文档已上传：{res['doc_id']}（{infos[0].get('fileName')}）")

    # 轮询向量化状态：上传成功 ≠ 可检索，必须等 embedding_stat == 1
    deadline = time.time() + POLL_DEADLINE
    while True:
        r = call_api("GET", f"{BASE}/llm-application/open/document/{res['doc_id']}")
        if not code_ok(r):
            return None, f"查询文档状态失败 code={r.get('code')} message={r.get('message')}"
        stat = (r.get("data") or {}).get("embedding_stat")
        if stat == 1:
            break
        if stat == 2:
            fail = (r.get("data") or {}).get("failInfo") or {}
            return None, (f"向量化失败 embedding_code={fail.get('embedding_code')} "
                          f"embedding_msg={fail.get('embedding_msg')}")
        if time.time() >= deadline:
            return None, f"等待向量化超时（>{POLL_DEADLINE}s，最后 embedding_stat={stat}）"
        time.sleep(POLL_INTERVAL)
    print(f"  [3/4] 向量化完成（embedding_stat=1）")

    r = call_api("POST", f"{BASE}/llm-application/open/knowledge/retrieve",
                 json={"query": QUERY, "knowledge_ids": [res["kb_id"]], "top_k": TOP_K})
    if not code_ok(r):
        return None, f"检索失败 code={r.get('code')} message={r.get('message')}"
    hits = r.get("data") or []
    if not hits:
        return None, "检索返回空数组（无命中切片）"
    print(f"  [4/4] 检索到 {len(hits)} 条切片")
    return [{"text": h.get("text", ""), "score": h.get("score"),
             "doc_name": (h.get("metadata") or {}).get("doc_name")} for h in hits], None


# ---------------------------------------------------------------- 方案二：Embeddings 自建向量检索

def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve_via_embeddings(lines):
    def embed(texts):
        r = call_api("POST", f"{BASE}/paas/v4/embeddings",
                     json={"model": EMB_MODEL, "input": texts, "dimensions": EMB_DIM})
        if "data" not in r:
            return None, f"embeddings 响应异常：{str(r)[:200]}"
        out = [d["embedding"] for d in sorted(r["data"], key=lambda d: d.get("index", 0))]
        if len(out) != len(texts):
            return None, f"embeddings 返回数量不符（{len(out)}/{len(texts)}）"
        return out, None

    vecs = []
    for i in range(0, len(lines), EMB_BATCH):
        batch, err = embed([t for _, t in lines[i:i + EMB_BATCH]])
        if err:
            return None, err
        vecs.extend(batch)
        print(f"  已向量化 {min(i + EMB_BATCH, len(lines))}/{len(lines)} 条 FAQ")
    qv, err = embed([QUERY])
    if err:
        return None, err

    sims = sorted(((_cosine(qv[0], v), no, t) for v, (no, t) in zip(vecs, lines)),
                  key=lambda x: x[0], reverse=True)
    top = sims[:20]  # 先召回 top20，再用 rerank 精排

    try:  # rerank 尽力而为，失败则直接用向量相似度顺序
        r = call_api("POST", f"{BASE}/paas/v4/rerank",
                     json={"model": "rerank", "query": QUERY,
                           "documents": [t for _, _, t in top],
                           "top_n": TOP_K, "return_documents": False})
        results = r.get("results") or []
        if results:
            print(f"  rerank 精排完成（{len(results)} 条）")
            return [{"text": top[it["index"]][2], "score": it.get("relevance_score"),
                     "line_no": top[it["index"]][1]} for it in results], None
    except Exception:
        pass

    return [{"text": t, "score": s, "line_no": no} for s, no, t in top[:TOP_K]], None


# ---------------------------------------------------------------- 方案三：本地词法检索

def _bigrams(s):
    s = "".join(ch for ch in s if not ch.isspace())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def retrieve_via_local(lines):
    q = _bigrams(QUERY)
    scored = []
    for no, text in lines:
        d = _bigrams(text)
        scored.append((len(q & d) / len(q) if q else 0.0, no, text))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"text": t, "score": s, "line_no": no} for s, no, t in scored[:TOP_K]]


# ---------------------------------------------------------------- 清理与主流程

def cleanup(res):
    if not (res.get("kb_id") or res.get("doc_id")):
        return
    print("\n----- 清理临时资源 -----")
    if res.get("doc_id"):
        try:
            r = call_api("DELETE", f"{BASE}/llm-application/open/document/{res['doc_id']}")
            print(f"  删除文档 {res['doc_id']}：code={r.get('code')} message={r.get('message')}")
        except Exception as e:
            print(f"  删除文档 {res['doc_id']} 失败：{describe_exc(e)}")
    if res.get("kb_id"):
        try:
            r = call_api("DELETE", f"{BASE}/llm-application/open/knowledge/{res['kb_id']}")
            print(f"  删除知识库 {res['kb_id']}：code={r.get('code')} message={r.get('message')}")
        except Exception as e:
            print(f"  删除知识库 {res['kb_id']} 失败：{describe_exc(e)}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if FAQ_PATH is None:
        print("错误：在脚本同目录和当前目录都找不到 faq.txt", file=sys.stderr)
        return 2
    lines = load_faq_lines()
    print(f"FAQ 库：{FAQ_PATH}（{len(lines)} 条）")
    print(f"检索问题：{QUERY}")

    if API_KEY:
        res = {}
        print("\n----- 方案一：托管知识库 -----")
        try:
            hits, err = retrieve_via_hosted_kb(res)
        except Exception as e:
            hits, err = None, describe_exc(e)
        finally:
            cleanup(res)  # 无论成败都删除已创建的文档与知识库
        if hits:
            print_results("托管知识库", hits)
            return 0
        print(f"托管知识库未走通：{err}")

        print("\n----- 方案二：Embeddings 自建向量检索 -----")
        try:
            hits, err = retrieve_via_embeddings(lines)
        except Exception as e:
            hits, err = None, describe_exc(e)
        if hits:
            print_results("智谱 Embeddings + Rerank 自建检索", hits)
            print("（本方案只做无状态向量计算，不在服务端留下任何资源，无需清理）")
            return 0
        print(f"Embeddings 方案未走通：{err}")
    else:
        print("未检测到 ZHIPUAI_API_KEY，跳过需要联网的方案一/二，直接使用本地检索。")

    print("\n----- 方案三：本地词法检索 -----")
    hits = retrieve_via_local(lines)
    print_results("本地字符 bigram 词法检索", hits)
    print("（本方案纯本地计算，不产生任何远端资源，无需清理）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
