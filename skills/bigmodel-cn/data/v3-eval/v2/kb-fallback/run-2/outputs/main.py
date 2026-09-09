#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 main.py 同目录的 faq.txt 灌进智谱开放平台（bigmodel.cn）的托管知识库，
然后用「退换货政策的有效期是多久」检索，把检索到的原文片段打印出来。

检索按三级路线走，保证只要 faq.txt 有内容就一定有检索结果输出：
  路线一（主路径）：托管知识库——建库 → 上传 faq.txt → 轮询向量化状态 →
                   POST /llm-application/open/knowledge/retrieve 检索。
  路线二（替代）：自建管线——embedding-3 全量向量化 + 余弦相似度召回 +
                   rerank 精排（rerank 不可用时直接用余弦排序）。
  路线三（兜底）：本地字符 bigram 词面匹配，不调用任何 API。

无论走哪条路，托管知识库里建出来的临时资源（文档 + 知识库）都会删除。

已知平台陷阱（实测，官方文档没写清，代码里已处理）：
  * llm-application/open/* 这族接口出错时 HTTP 状态码仍是 200，
    真实结果在响应体的 code 字段里，必须判 body["code"] == 200。
  * 文档上传成功 ≠ 可检索：向量化是后台异步的，失败时检索端只会
    返回空数组。必须轮询 GET /document/{id} 的 embedding_stat
    （0=处理中 1=就绪 2=失败），就绪了再去检索。

用法：
    export ZHIPUAI_API_KEY=你的key
    python3 main.py

退出码：0 = 走通了 API 检索（路线一或路线二）；
        2 = 只有本地兜底检索成功（API 全程不可用）；
        1 = 彻底失败（连本地匹配也没有结果）。
"""

import math
import os
import sys
import time

import requests

BASE = "https://open.bigmodel.cn/api"
FAQ_NAME = "faq.txt"
QUERY = "退换货政策的有效期是多久"
TOP_K = 5                # 最终打印的片段条数
EMBED_BATCH = 64         # embedding-3 单次 input 数组上限 64 条
RECALL_N = 20            # 路线二中送入 rerank 的召回条数（rerank 上限 128）
POLL_INTERVAL = 5        # 向量化轮询间隔（秒）
POLL_DEADLINE = 180      # 向量化轮询总超时（秒）


class ApiError(Exception):
    """统一的接口失败异常，message 里带上下文，方便直接打印降级原因。"""


# ---------------------------------------------------------------- HTTP 基础

def _request(method, url, **kw):
    """带简单重试的请求：网络异常 / HTTP 5xx 重试 3 次，其余原样返回。"""
    kw.setdefault("timeout", 60)
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.request(method, url, **kw)
        except requests.RequestException as err:
            last_err = err
            time.sleep(1 + attempt)
            continue
        if resp.status_code >= 500 and attempt < 2:
            time.sleep(1 + attempt)
            continue
        return resp
    raise ApiError(f"{method} {url} 重试 3 次仍失败：{last_err}")


def _auth(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def kb_call(method, path, api_key, **kw):
    """托管知识库这族接口的调用器。

    坑：这族接口出错时 HTTP 也是 200，必须判 body.code == 200，
    否则流水线会带着错误继续跑。
    """
    resp = _request(method, BASE + path, headers=_auth(api_key), **kw)
    try:
        body = resp.json()
    except ValueError:
        raise ApiError(
            f"{method} {path}: HTTP {resp.status_code}，响应不是 JSON：{resp.text[:200]}")
    code = body.get("code", resp.status_code)
    if resp.status_code != 200 or code != 200:
        raise ApiError(
            f"{method} {path}: HTTP {resp.status_code}，"
            f"code={code}，message={body.get('message')}")
    return body.get("data")


def paas_call(path, api_key, payload):
    """标准 paas/v4 接口（embeddings / rerank）的调用器，出错时看 HTTP 和 error 字段。"""
    resp = _request("POST", BASE + path, headers=_auth(api_key), json=payload)
    try:
        body = resp.json()
    except ValueError:
        raise ApiError(
            f"POST {path}: HTTP {resp.status_code}，响应不是 JSON：{resp.text[:200]}")
    if resp.status_code != 200 or body.get("error"):
        raise ApiError(
            f"POST {path}: HTTP {resp.status_code}，error={body.get('error')}")
    return body


# ---------------------------------------------------------------- 路线一：托管知识库

def cleanup_kb(api_key, knowledge_id, document_id):
    """删除本次运行创建的临时文档和知识库。删除知识库会连带删掉库内文档。"""
    if not knowledge_id:
        return
    if document_id:
        try:
            kb_call("DELETE", f"/llm-application/open/document/{document_id}", api_key)
            print(f"[清理] 临时文档已删除：{document_id}")
        except ApiError as err:
            print(f"[清理] 警告：删除文档失败（继续删知识库）：{err}")
    try:
        kb_call("DELETE", f"/llm-application/open/knowledge/{knowledge_id}", api_key)
        print(f"[清理] 临时知识库已删除：{knowledge_id}")
    except ApiError as err:
        print(f"[清理] 警告：删除知识库失败，请到控制台手动删除 {knowledge_id}：{err}")


def try_hosted_kb(api_key, faq_path, query):
    """主路径：托管知识库灌入 + 检索。任何一步失败抛 ApiError，由上层降级。"""
    knowledge_id = None
    document_id = None
    try:
        # 1) 创建知识库（embedding_id=11 即 Embedding-3）
        data = kb_call(
            "POST", "/llm-application/open/knowledge", api_key,
            json={
                "embedding_id": 11,
                "name": f"faq-tmp-{int(time.time())}",
                "description": "临时知识库：main.py 检索验证用，结束即删",
            }) or {}
        knowledge_id = data.get("id")
        if not knowledge_id:
            raise ApiError(f"创建知识库返回里没有 id：{data}")
        print(f"[KB] 知识库已创建：{knowledge_id}")

        # 2) 上传 faq.txt。faq.txt 是一行一条的短句，用 knowledge_type=5
        #    （自定义切分）+ 分隔符 \n，让每行成为一个切片，检索精度最好。
        with open(faq_path, "rb") as fh:
            data = kb_call(
                "POST",
                f"/llm-application/open/document/upload_document/{knowledge_id}",
                api_key, timeout=120,
                files={"files": (os.path.basename(faq_path), fh, "text/plain")},
                data=[("knowledge_type", "5"),
                      ("custom_separator", "\n"),
                      ("sentence_size", "100")]) or {}
        infos = data.get("successInfos") or []
        fails = data.get("failedInfos") or []
        if fails or not infos:
            raise ApiError(f"文档上传失败：failedInfos={fails}，successInfos={infos}")
        document_id = infos[0].get("documentId")
        if not document_id:
            raise ApiError(f"上传成功但没有 documentId：{infos}")
        print(f"[KB] 文档已上传：{document_id}（{infos[0].get('fileName')}）")

        # 3) 轮询向量化状态。坑：上传成功 ≠ 可检索，后台向量化失败时
        #    检索端只会返回空数组，必须看 embedding_stat 才知道真相。
        deadline = time.time() + POLL_DEADLINE
        while True:
            doc = kb_call(
                "GET", f"/llm-application/open/document/{document_id}", api_key) or {}
            stat = doc.get("embedding_stat")
            if stat == 1:
                print("[KB] 向量化完成，文档可检索")
                break
            if stat == 2:
                raise ApiError(f"向量化失败：failInfo={doc.get('failInfo')}")
            if time.time() > deadline:
                raise ApiError(f"等待向量化超时（最后状态 embedding_stat={stat}）")
            print(f"[KB] 向量化处理中（embedding_stat={stat}），{POLL_INTERVAL} 秒后重查…")
            time.sleep(POLL_INTERVAL)

        # 4) 检索。先带 rerank 精排；账号没开重排就退回普通混合检索。
        base_payload = {
            "query": query,
            "knowledge_ids": [knowledge_id],
            "top_k": TOP_K,
            "top_n": 20,
            "recall_method": "mixed",
        }
        try:
            data = kb_call(
                "POST", "/llm-application/open/knowledge/retrieve", api_key,
                json=dict(base_payload, rerank_status=1, rerank_model="rerank"))
        except ApiError as err:
            print(f"[KB] 带重排的检索失败，改用普通混合检索重试：{err}")
            data = kb_call(
                "POST", "/llm-application/open/knowledge/retrieve", api_key,
                json=base_payload)

        items = data if isinstance(data, list) else ((data or {}).get("list") or [])
        if not items:
            # 文档已就绪仍召回为空：本文件里就有近乎原句的问题，
            # 空结果只能说明这条链路在这个账号上不可用，交给上层降级。
            raise ApiError("检索返回空数组（文档 embedding_stat=1 却无召回）")

        return [{"text": it.get("text", ""),
                 "score": it.get("score", 0.0),
                 "from": f"知识库切片 {it.get('metadata', {}).get('_id', '')}".strip()}
                for it in items]

    finally:
        # 无论成功、失败还是异常，都把临时资源删掉
        cleanup_kb(api_key, knowledge_id, document_id)


# ---------------------------------------------------------------- 路线二：embeddings + rerank

def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def try_embed_rerank(api_key, lines, query):
    """替代路径：自己拼检索管线。全量向量化 → 余弦召回 → rerank 精排。"""
    texts = [query] + list(lines)          # 下标 0 是 query，1..n 是原文行
    vectors = [None] * len(texts)
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        body = paas_call("/paas/v4/embeddings", api_key,
                         {"model": "embedding-3",
                          "input": batch,
                          "dimensions": 1024})
        for item in body.get("data", []):
            vectors[start + item["index"]] = item["embedding"]
        print(f"[RAG] 已向量化 {min(start + EMBED_BATCH, len(texts))}/{len(texts)} 条")
    if any(v is None for v in vectors):
        raise ApiError("embeddings 返回的向量数量与输入不一致")

    scored = sorted(((_cosine(vectors[0], vectors[i + 1]), i) for i in range(len(lines))),
                    reverse=True)
    recall = scored[:RECALL_N]
    print(f"[RAG] 余弦召回 Top{RECALL_N}（最高 {recall[0][0]:.4f}），送 rerank 精排")

    recall_idx = [i for _, i in recall]
    try:
        body = paas_call("/paas/v4/rerank", api_key,
                         {"model": "rerank",
                          "query": query,
                          "documents": [lines[i] for i in recall_idx],
                          "top_n": TOP_K,
                          "return_documents": False})
        # results[].index 对应我发过去的 documents 数组下标，映射回原文行
        return [{"text": lines[recall_idx[r["index"]]],
                 "score": r.get("relevance_score", 0.0),
                 "from": "rerank"}
                for r in body.get("results", [])][:TOP_K]
    except ApiError as err:
        print(f"[RAG] rerank 不可用，直接用余弦相似度排序：{err}")
        return [{"text": lines[i], "score": s, "from": "cosine"}
                for s, i in recall[:TOP_K]]


# ---------------------------------------------------------------- 路线三：本地兜底

def _bigrams(s):
    s = "".join(s.split())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}


def local_match(lines, query):
    """不调 API 的最后兜底：字符 bigram 的 Jaccard 相似度词面检索。"""
    qb = _bigrams(query)
    scored = []
    for i, line in enumerate(lines):
        lb = _bigrams(line)
        union = len(qb | lb) or 1
        scored.append((len(qb & lb) / union, i))
    scored.sort(reverse=True)
    return [{"text": lines[i], "score": s, "from": "local-bigram"}
            for s, i in scored[:TOP_K] if s > 0]


# ---------------------------------------------------------------- 输出与主流程

def print_snippets(title, items):
    print(f"\n===== 检索到的原文片段（{title}） =====")
    for rank, it in enumerate(items, 1):
        try:
            score = f"{it['score']:.4f}"
        except (TypeError, ValueError):
            score = str(it.get("score"))
        print(f"[{rank}] score={score}  来源={it.get('from', '')}")
        print(f"    {it['text']}")
    print()


def load_faq():
    """优先读 main.py 同目录的 faq.txt，其次当前工作目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for base_dir in (here, os.getcwd()):
        path = os.path.join(base_dir, FAQ_NAME)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                lines = [ln.strip() for ln in fh if ln.strip()]
            if not lines:
                sys.exit(f"错误：{path} 没有非空内容，无法灌库")
            print(f"[OK] 已读取 {path}（{len(lines)} 个非空片段）")
            return path, lines
    sys.exit(f"错误：在 {here} 和 {os.getcwd()} 都找不到 {FAQ_NAME}，"
             f"请把它放到 main.py 同目录后重跑")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：环境变量 ZHIPUAI_API_KEY 未设置（export ZHIPUAI_API_KEY=你的key）")

    faq_path, lines = load_faq()
    print(f"检索问题：{QUERY}\n")

    # 路线一：托管知识库（内部 finally 保证清理）
    try:
        items = try_hosted_kb(api_key, faq_path, QUERY)
        print_snippets("智谱托管知识库 /llm-application/open/knowledge/retrieve", items)
        return 0
    except Exception as err:  # 任何一步走不通都降级，不让流水线死在这里
        print(f"\n[降级] 托管知识库路径在本账号上不可用：{err}\n")

    # 路线二：embeddings + rerank 自建检索管线
    try:
        items = try_embed_rerank(api_key, lines, QUERY)
        print_snippets("自建管线：embedding-3 召回 + rerank 精排", items)
        return 0
    except Exception as err:
        print(f"\n[降级] embeddings/rerank 管线不可用：{err}\n")

    # 路线三：本地词面匹配兜底（保证一定有检索结果打印）
    items = local_match(lines, QUERY)
    if not items:
        print("错误：所有检索路线都失败，且本地匹配无结果")
        return 1
    print("[兜底] API 全程不可用，以下为本地 bigram 词面匹配结果（未调用任何 API）")
    print_snippets("本地 bigram 词面匹配（兜底）", items)
    return 2


if __name__ == "__main__":
    sys.exit(main())
