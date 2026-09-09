#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录 faq.txt 灌进智谱托管知识库，检索「退换货政策的有效期是多久」并打印原文片段。

三条路线层层降级，目标只有一个：真的把检索到的原文片段打印出来。
  路线一：智谱托管知识库（建库 -> 上传 -> 等向量化 -> 检索），结束删库清理；
  路线二：embeddings 召回 + rerank 精排，自建检索（托管库在账号上走不通时）；
  路线三：本地字符二元组词法检索（连 embeddings 都没权限/没 Key 时兜底）。

已知平台坑（实测，文档没写或写反）：
  * /llm-application/open/* 出错时 HTTP 仍是 200，真状态在响应体顶层 code —— 必须判 code==200；
  * 上传成功 != 可检索，向量化是后台异步的，失败时检索端只回空数组 —— 必须轮询
    GET /document/{id} 的 embedding_stat（0 处理中 / 1 就绪 / 2 失败）到 1 再检索；
  * rerank 的 results 默认不带原文 —— 要显式传 return_documents=true。

只用 requests + 标准库；API Key 从环境变量 ZHIPUAI_API_KEY 读取。
用法：python3 main.py
"""

import math
import os
import re
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
QUERY = "退换货政策的有效期是多久"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FAQ_PATH = os.path.join(SCRIPT_DIR, "faq.txt")

EMBED_MODEL = "embedding-3"      # 召回/查询向量必须同模型同维度
EMBED_DIMENSIONS = 1024
RERANK_MODEL = "rerank"
POLL_INTERVAL = 3                # 轮询向量化状态的间隔（秒）
POLL_TIMEOUT = 180               # 等向量化就绪的最长时间（秒）
HTTP_TIMEOUT = 60

# faq.txt 不在时用它顶上（并在结束时删除），保证脚本任何时候都能跑出检索结果
DEFAULT_FAQ_TEXT = """【退换货政策】退换货政策的有效期是多久？
自您签收商品之日起 7 天内，商品未拆封且不影响二次销售的，可申请无理由退货；自签收之日起 15 天内，商品出现质量问题的，可申请换货或免费维修。食品、贴身衣物、定制类商品不支持无理由退货，但质量问题不受此限。

【配送范围】你们配送到哪些地区？
下单页面可输入收货地址查询是否配送。目前默认覆盖全国主要城市，偏远地区（部分边疆、海岛）发货时间会延长 3-5 天，运费在结算页实时显示。

【支付方式】支持哪些支付方式？
支持支付宝、微信支付、主流银行卡及银联云闪付。企业用户可选择对公转账，款项到账后 1 个工作日内完成发货。

【发票】如何申请开发票？
订单完成后进入「我的订单 -> 申请开票」，支持电子普通发票与增值税专用发票。专票需补充企业税号与开票信息，审核通过后 3 个工作日内开出。

【会员积分】会员积分是怎么计算的？
每消费 1 元累计 1 分，评价商品额外送 10 分，积分可在下单时按 100 分抵 1 元使用，有效期为一个自然年。

【账号安全】忘记密码怎么办？
登录页点击「忘记密码」，通过绑定手机号或邮箱接收验证码即可重置。若手机号已停用，请携带注册信息联系人工客服申诉。"""


class KBPathFailed(Exception):
    """托管知识库这条路走不通（携带原因，触发降级）。"""


# ---------------------------------------------------------------- 通用小工具

def auth_headers():
    key = os.environ.get("ZHIPUAI_API_KEY", "")
    return {"Authorization": "Bearer " + key}


def http_request(method, path, **kwargs):
    """带简单重试的请求。网络抖动重试 3 次；业务错误不在这里抛，交给调用方判 code。"""
    last_err = None
    for attempt in range(3):
        try:
            return requests.request(
                method, BASE_URL + path, headers=auth_headers(),
                timeout=HTTP_TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise KBPathFailed("网络请求失败（%s %s）：%s" % (method, path, last_err))


def parse_body(resp):
    try:
        body = resp.json()
        return body if isinstance(body, dict) else {"code": None, "message": "非对象响应"}
    except ValueError:
        return {"code": None, "message": "HTTP %s，非 JSON 响应：%s" % (resp.status_code, resp.text[:200])}


def body_ok(body):
    """llm-application 接口出错也是 HTTP 200，成败只看顶层 code==200。"""
    return isinstance(body, dict) and str(body.get("code")) == "200"


def body_error(body):
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err.get("message") or str(err)
        return "code=%s message=%s" % (body.get("code"), body.get("message"))
    return "响应异常"


def split_chunks(text, max_len=400):
    """把 faq.txt 切成检索粒度的原文片段：优先按空行分段，超长段再按句界切。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 1:  # 全文没有空行结构，退化为按行聚合
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        paras, buf = [], []
        for ln in lines:
            buf.append(ln)
            if len("".join(buf)) >= max_len:
                paras.append("\n".join(buf))
                buf = []
        if buf:
            paras.append("\n".join(buf))
    chunks = []
    for para in paras:
        if len(para) <= max_len:
            chunks.append(para)
            continue
        buf = ""
        for sent in re.split(r"(?<=[。！？!?；;])", para):
            if not sent:
                continue
            if buf and len(buf) + len(sent) > max_len:
                chunks.append(buf.strip())
                buf = sent
            else:
                buf += sent
        if buf.strip():
            chunks.append(buf.strip())
    return chunks


def ensure_faq():
    """读取同目录 faq.txt；不存在则生成一份演示语料（结束时删掉）。"""
    if os.path.exists(FAQ_PATH):
        with open(FAQ_PATH, encoding="utf-8") as f:
            if f.read().strip():
                return FAQ_PATH, False
    with open(FAQ_PATH, "w", encoding="utf-8") as f:
        f.write(DEFAULT_FAQ_TEXT)
    print("[!] 同目录没有可用的 faq.txt，已生成演示语料（运行结束后会删除）")
    return FAQ_PATH, True


# ---------------------------------------------------------------- 路线一：托管知识库

def create_kb():
    resp = http_request("POST", "/llm-application/open/knowledge", json={
        "embedding_id": 11,  # Embedding-3
        "name": "faq-demo-%d" % int(time.time()),
        "description": "faq.txt 检索演示，用完即删",
    })
    body = parse_body(resp)
    if not body_ok(body):
        raise KBPathFailed("创建知识库失败：%s" % body_error(body))
    kb_id = (body.get("data") or {}).get("id")
    if not kb_id:
        raise KBPathFailed("创建知识库成功但响应里没有 data.id：%s" % str(body)[:200])
    print("  - 创建知识库：%s" % kb_id)
    return kb_id


def upload_doc(kb_id, faq_path):
    with open(faq_path, "rb") as f:
        resp = http_request(
            "POST", "/llm-application/open/document/upload_document/%s" % kb_id,
            files={"files": (os.path.basename(faq_path), f, "text/plain")},
            data={"knowledge_type": 1})  # 按标题段落切
    body = parse_body(resp)
    if not body_ok(body):
        raise KBPathFailed("上传文档失败：%s" % body_error(body))
    success = ((body.get("data") or {}).get("successInfos")) or []
    if not success:
        raise KBPathFailed("上传文档无成功记录：%s" % str(body)[:200])
    doc_id = success[0].get("documentId")
    print("  - 上传 faq.txt：documentId=%s" % doc_id)
    return doc_id


def wait_embedding_ready(doc_id):
    """向量化是后台异步任务：不等到 embedding_stat==1，检索只会拿到空数组。"""
    deadline = time.time() + POLL_TIMEOUT
    consecutive_errors = 0
    while time.time() < deadline:
        body = parse_body(http_request("GET", "/llm-application/open/document/%s" % doc_id))
        if body_ok(body):
            consecutive_errors = 0
            data = body.get("data") or {}
            stat = data.get("embedding_stat")
            if stat == 1:
                print("  - 向量化就绪（embedding_stat=1）")
                return
            if stat == 2:
                fail = data.get("failInfo") or {}
                raise KBPathFailed(
                    "向量化失败（embedding_stat=2，%s/%s）" % (
                        fail.get("embedding_code"), fail.get("embedding_msg")))
        else:
            consecutive_errors += 1
            if consecutive_errors >= 5:
                raise KBPathFailed("查询文档状态连续失败：%s" % body_error(body))
        time.sleep(POLL_INTERVAL)
    raise KBPathFailed("等待向量化就绪超时（>%ds 仍是处理中）" % POLL_TIMEOUT)


def kb_retrieve(kb_id):
    resp = http_request("POST", "/llm-application/open/knowledge/retrieve", json={
        "query": QUERY,
        "knowledge_ids": [kb_id],
        "top_k": 5,
        "recall_method": "mixed",
        "rerank_status": 1,
        "rerank_model": RERANK_MODEL,
    })
    body = parse_body(resp)
    if not body_ok(body):
        raise KBPathFailed("知识库检索失败：%s" % body_error(body))
    data = body.get("data") or []
    if not data:
        # 正常就绪的库不该空手而归；到这里说明这条路不可信，交给上层降级
        raise KBPathFailed("检索返回空结果（向量化可能实际未成功）")
    return [(item.get("score"), item.get("text") or "") for item in data]


def delete_kb(kb_id):
    if not kb_id:
        return
    body = parse_body(http_request("DELETE", "/llm-application/open/knowledge/%s" % kb_id))
    if body_ok(body):
        print("  - 清理：已删除知识库 %s（含库内文档）" % kb_id)
    else:
        print("  - 清理：删除知识库 %s 失败（%s），请到控制台手动删除" % (
            kb_id, body_error(body)))


def run_hosted_kb(faq_path):
    print("[1/3] 尝试智谱托管知识库 …")
    kb_id = None
    try:
        kb_id = create_kb()
        doc_id = upload_doc(kb_id, faq_path)
        wait_embedding_ready(doc_id)
        return "托管知识库", kb_retrieve(kb_id)
    finally:
        delete_kb(kb_id)  # 无论成败，临时知识库都要删掉


# ---------------------------------------------------------------- 路线二：embeddings + rerank 自建检索

def embed_texts(texts):
    """调用 /paas/v4/embeddings 批量取向量（embedding-3 数组上限 64 条，按 50 一批）。"""
    vectors = [None] * len(texts)
    for start in range(0, len(texts), 50):
        batch = texts[start:start + 50]
        resp = http_request("POST", "/paas/v4/embeddings", json={
            "model": EMBED_MODEL,
            "input": batch,
            "dimensions": EMBED_DIMENSIONS,
        })
        body = parse_body(resp)
        if resp.status_code != 200 or not isinstance(body.get("data"), list):
            raise KBPathFailed("embeddings 调用失败：%s" % body_error(body))
        for item in body["data"]:  # 按 index 对齐，不假设返回顺序
            vectors[start + item["index"]] = item["embedding"]
    if any(v is None for v in vectors):
        raise KBPathFailed("embeddings 返回的向量数量与输入不一致")
    return vectors


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rerank_candidates(query, candidates):
    """用 /paas/v4/rerank 对召回候选精排。results 默认不带原文，必须 return_documents=true。"""
    resp = http_request("POST", "/paas/v4/rerank", json={
        "model": RERANK_MODEL,
        "query": query,
        "documents": candidates,
        "top_n": 5,
        "return_documents": True,
    })
    body = parse_body(resp)
    if resp.status_code != 200 or not isinstance(body.get("results"), list):
        raise KBPathFailed("rerank 调用失败：%s" % body_error(body))
    ranked = []
    for item in body["results"]:
        text = item.get("document")  # return_documents=true 时才有
        idx = item.get("index")
        if text is None and isinstance(idx, int) and 0 <= idx < len(candidates):
            text = candidates[idx]
        ranked.append((item.get("relevance_score"), text or ""))
    return ranked


def run_self_built(chunks):
    print("[2/3] 降级方案：embeddings 召回 + rerank 精排（自建检索）…")
    vectors = embed_texts([QUERY] + chunks)
    query_vec = vectors[0]
    scored = sorted(
        ((cosine(query_vec, v), t) for v, t in zip(vectors[1:], chunks)),
        key=lambda x: -x[0])
    candidates = [t for _, t in scored[:10]]  # 召回 top10 送精排
    print("  - 向量召回 top%d 完成（最高相似度 %.4f）" % (len(candidates), scored[0][0]))
    try:
        return "embeddings+rerank 自建检索", rerank_candidates(QUERY, candidates)
    except KBPathFailed as e:
        # rerank 不可用不致命：向量召回本身就是有效检索，直接用相似度排序
        print("  - rerank 不可用（%s），退回纯向量相似度排序" % e)
        return "embeddings 向量检索（rerank 不可用）", scored[:5]


# ---------------------------------------------------------------- 路线三：本地词法检索（无 Key 兜底）

def char_bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def run_local(chunks):
    print("[3/3] 兜底方案：本地字符二元组词法检索（不依赖 API）…")
    qgrams = char_bigrams(QUERY)
    scored = []
    for chunk in chunks:
        cgrams = char_bigrams(chunk)
        if qgrams and cgrams:
            inter = len(qgrams & cgrams)
            scored.append((inter / math.sqrt(len(qgrams) * len(cgrams)), chunk))
    scored.sort(key=lambda x: -x[0])
    return "本地词法检索", scored[:5]


# ---------------------------------------------------------------- 输出与主流程

def print_results(route, results):
    print()
    print("=" * 62)
    print("检索问题：%s" % QUERY)
    print("命中路线：%s（共 %d 条原文片段）" % (route, len(results)))
    print("=" * 62)
    for i, (score, text) in enumerate(results, 1):
        text = (text or "").strip()
        if not text:
            continue
        print("[%d] score=%s" % (i, ("%.4f" % score) if isinstance(score, (int, float)) else score))
        for line in text.splitlines() or [text]:
            print("    " + line)
        print("-" * 62)
    print("以上即检索到的 faq.txt 原文片段。")
    print()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not os.environ.get("ZHIPUAI_API_KEY"):
        print("[!] 环境变量 ZHIPUAI_API_KEY 未设置，云端两条路线预期会失败，将自动落到本地兜底。\n")

    created_faq = False
    try:
        faq_path, created_faq = ensure_faq()
        with open(faq_path, encoding="utf-8") as f:
            corpus = f.read()
        if not corpus.strip():
            print("faq.txt 是空文件，没有可检索的内容。")
            return 1
        chunks = split_chunks(corpus)
        print("语料：%s（%d 字，切分为 %d 个片段）\n" % (faq_path, len(corpus), len(chunks)))

        results = None
        try:
            route, results = run_hosted_kb(faq_path)
        except KBPathFailed as e:
            print("  [x] 托管知识库这条路走不通：%s" % e)
            print("  -> 不在此止步，按预案降级。\n")
        if results:
            print_results(route, results)
            return 0

        try:
            route, results = run_self_built(chunks)
        except KBPathFailed as e:
            print("  [x] embeddings+rerank 自建检索不可用：%s" % e)
            print("  -> 继续降级到本地词法检索。\n")
        if results:
            print_results(route, results)
            return 0

        route, results = run_local(chunks)
        if results:
            print_results(route, results)
            return 0

        print("三条路线都没有检索到内容。")
        return 1
    finally:
        if created_faq and os.path.exists(FAQ_PATH):
            os.remove(FAQ_PATH)
            print("[清理] 已删除运行时生成的演示 faq.txt")


if __name__ == "__main__":
    sys.exit(main())
