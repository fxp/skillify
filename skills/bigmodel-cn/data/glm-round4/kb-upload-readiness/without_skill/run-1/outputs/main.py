#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱（BigModel）托管知识库，并做真实检索校验。

流程：
    读取 faq.txt → 创建临时知识库 → 上传文档 → 【核心】真实检索验证 → 删除知识库

核心承诺（这个脚本存在的意义）：
    上传接口返回"成功" ≠ 文档可检索：解析和向量化都是异步的，向量索引没建好
    之前检索永远返回空（很容易被坑）。所以本脚本在宣布成功之前，必须用官方检索
    接口真实地召回 faq.txt 的内容——命中切片要么文档 id/文件名对得上，要么文本
    内容确实出自 faq.txt 原文（双保险），否则一律按失败处理：明确报错、给出
    诊断信息和可能原因，绝不报喜不报忧。最后无论成败都会删除本次创建的知识库。

用法：
    export ZHIPUAI_API_KEY="你的key"
    python3 main.py            # faq.txt 与本脚本同目录

退出码：0 = 全流程成功且检索验证通过；1 = 任何环节失败（包括验证不通过）。
依赖：仅 requests + Python3 标准库。

接口依据智谱官方文档（docs.bigmodel.cn → API 参考 → 知识库 API，均为 Bearer 认证）：
    POST   /api/llm-application/open/knowledge                      创建知识库
    POST   /api/llm-application/open/document/upload_document/{id}  上传文件文档（multipart，字段名 files）
    GET    /api/llm-application/open/document/{id}                  文档详情（解析/向量化状态）
    GET    /api/llm-application/open/document?knowledge_id=…        文档列表（详情接口失败时兜底）
    POST   /api/llm-application/open/knowledge/retrieve             知识库检索（验证的核心）
    DELETE /api/llm-application/open/knowledge/{id}                 删除知识库
"""

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("缺少依赖库 requests，请先安装：pip3 install requests", file=sys.stderr)
    sys.exit(1)

# ---------------------------- 配置 ----------------------------
API_BASE = "https://open.bigmodel.cn/api"
EMBEDDING_ID = 11        # 向量化模型：3=Embedding-2 / 11=Embedding-3 / 12=Embedding-3-pro
VERIFY_TIMEOUT = 600     # 检索验证总等待秒数（文档解析+向量化是异步的，宁可等够）
POLL_INTERVAL = 10       # 每轮检索验证的间隔秒数
HTTP_TIMEOUT = 30        # 单次 HTTP 请求超时秒数
HTTP_RETRIES = 3         # 网络异常 / 429 / 5xx 的重试次数
HTTP_RETRY_BACKOFF = 2   # 重试退避基数秒（第 n 次重试前等待 n * 该值）
TRANSIENT_STATUS = {429, 500, 502, 503, 504}

URL_CREATE = f"{API_BASE}/llm-application/open/knowledge"
URL_KB_DETAIL = f"{API_BASE}/llm-application/open/knowledge/" + "{kb_id}"   # 也是删除接口
URL_UPLOAD = f"{API_BASE}/llm-application/open/document/upload_document/" + "{kb_id}"
URL_DOC_DETAIL = f"{API_BASE}/llm-application/open/document/" + "{doc_id}"
URL_DOC_LIST = f"{API_BASE}/llm-application/open/document"
URL_RETRIEVE = f"{API_BASE}/llm-application/open/knowledge/retrieve"

FAQ_NAME = "faq.txt"


class KBError(Exception):
    """知识库流程中任何一步的失败，message 面向用户、带完整原因。"""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def trunc_json(obj, limit=600):
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…(已截断)"


# ---------------------- HTTP 基础封装 ----------------------
def _parse_response(resp, action):
    try:
        payload = resp.json()
    except ValueError:
        raise KBError(f"{action}失败：HTTP {resp.status_code}，且响应不是 JSON：{resp.text[:300]!r}")
    if not isinstance(payload, dict):
        raise KBError(f"{action}失败：HTTP {resp.status_code}，响应 JSON 不是对象：{trunc_json(payload)}")
    biz_code = payload.get("code", resp.status_code)  # 平台约定 code==200 为成功
    try:
        biz_ok = int(biz_code) == 200
    except (TypeError, ValueError):
        biz_ok = False
    if resp.status_code != 200 or not biz_ok:
        raise KBError(f"{action}失败：HTTP {resp.status_code}，业务code={biz_code}，"
                      f"message={payload.get('message')!r}")
    return payload


def _request(method, url, api_key, action, **kwargs):
    """带 Bearer 鉴权、超时、临时性错误重试的统一入口；所有失败都转成 KBError。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    headers.update(kwargs.pop("headers", None) or {})
    kwargs["headers"] = headers
    last_error = ""
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            last_error = f"{action}失败：网络异常（{type(exc).__name__}: {exc}）"
        else:
            if resp.status_code in TRANSIENT_STATUS:
                last_error = f"{action}失败：HTTP {resp.status_code}（临时性错误）"
            else:
                return _parse_response(resp, action)
        if attempt < HTTP_RETRIES:
            time.sleep(HTTP_RETRY_BACKOFF * attempt)
    raise KBError(f"{last_error}；已重试 {HTTP_RETRIES} 次仍失败")


# ---------------------- 各步骤接口封装 ----------------------
def create_knowledge_base(api_key, name, description):
    payload = _request(
        "POST", URL_CREATE, api_key, "创建知识库",
        json={"embedding_id": EMBEDDING_ID, "name": name, "description": description},
    )
    data = payload.get("data") or {}
    kb_id = data.get("id") or data.get("knowledge_id")
    if not kb_id:
        raise KBError(f"创建知识库失败：响应 data 里没有知识库 id：{trunc_json(payload)}")
    return str(kb_id)


def upload_document(api_key, kb_id, file_name, file_bytes):
    payload = _request(
        "POST", URL_UPLOAD.format(kb_id=kb_id), api_key, "上传文档",
        files={"files": (file_name, file_bytes, "text/plain")},
    )
    data = payload.get("data") or {}
    failed = data.get("failedInfos") or []
    if failed:
        detail = "；".join(f"{item.get('fileName')}：{item.get('failReason')}" for item in failed)
        raise KBError(f"上传文档失败：平台明确返回失败：{detail}")
    success = data.get("successInfos") or []
    doc_id = None
    if success:
        doc_id = success[0].get("documentId") or success[0].get("document_id")
    if not doc_id:
        raise KBError(f"上传文档失败：响应里没有拿到 documentId：{trunc_json(payload)}")
    return str(doc_id)


def get_document(api_key, kb_id, doc_id):
    """查文档状态：优先文档详情接口，失败则用文档列表兜底。返回 (状态dict或None, 错误信息或None)。"""
    try:
        payload = _request("GET", URL_DOC_DETAIL.format(doc_id=doc_id), api_key, "查询文档详情")
        return payload.get("data") or {}, None
    except KBError as detail_err:
        try:
            payload = _request(
                "GET", URL_DOC_LIST, api_key, "查询文档列表",
                params={"knowledge_id": kb_id, "page": 1, "size": 50},
            )
            for item in (payload.get("data") or {}).get("list") or []:
                if str(item.get("id")) == str(doc_id):
                    return item, None
            return None, f"文档详情接口报错（{detail_err}），且文档列表中也找不到该文档"
        except KBError as list_err:
            return None, f"文档详情接口报错（{detail_err}）；文档列表接口也报错（{list_err}）"


def retrieve(api_key, kb_id, query, top_k=5):
    """真实调用知识库检索接口。返回切片列表（空列表 = 没检索到东西）。"""
    payload = _request(
        "POST", URL_RETRIEVE, api_key, f"知识库检索（query={query!r}）",
        json={"query": query, "knowledge_ids": [kb_id], "top_k": top_k},
    )
    data = payload.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise KBError(f"知识库检索返回结构异常（data 不是数组）：{trunc_json(payload)}")
    return data


def describe_knowledge_base(api_key, kb_id):
    """诊断用，尽量拿知识库详情；失败不影响主流程。"""
    try:
        payload = _request("GET", URL_KB_DETAIL.format(kb_id=kb_id), api_key, "查询知识库详情")
        return payload.get("data") or {}
    except KBError:
        return {}


def delete_knowledge_base(api_key, kb_id):
    _request("DELETE", URL_KB_DETAIL.format(kb_id=kb_id), api_key, "删除知识库")


# ---------------------- 检索验证（核心） ----------------------
def text_from_faq(result_text, faq_no_ws, window=12, step=4):
    """判断检索回来的切片文本是否真的出自 faq.txt 原文（比对时忽略空白差异）。"""
    compact = "".join(result_text.split())
    if not compact:
        return False
    if len(compact) <= window:
        return compact in faq_no_ws
    for i in range(0, len(compact) - window + 1, step):
        if compact[i:i + window] in faq_no_ws:
            return True
    return False


def find_verified_hit(results, doc_id, file_name, faq_no_ws):
    """在检索结果里找一条能证明 faq.txt 可被检索的切片。

    认定标准（满足其一即可，双保险）：
      1) 切片 metadata 的 doc_id / doc_name 对得上本次上传的文档；
      2) 切片文本内容确实出现在 faq.txt 原文中。
    """
    for item in results:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or ""
        if not text:
            continue
        meta = item.get("metadata") or {}
        doc_match = (str(meta.get("doc_id") or "") == str(doc_id)
                     or meta.get("doc_name") == file_name)
        if doc_match or text_from_faq(text, faq_no_ws):
            return item
    return None


def wait_until_retrievable(api_key, kb_id, doc_id, file_name, queries, faq_no_ws):
    """核心环节：轮询真实检索，直到真的召回 faq.txt 的内容才算数。

    - 文档一旦向量化明确失败（failInfo 带错误码），立即报错，不空等；
    - 任一查询词命中可认定的切片（文档对得上 或 内容对得上）即通过；
    - 超时仍未召回 → 返回失败标志 + 诊断材料，由调用方打印原因。
    """
    log(f"开始检索验证：用 {len(queries)} 个取自 faq.txt 的查询词真实调用检索接口，"
        f"直到能召回 faq.txt 内容为止（最多等 {VERIFY_TIMEOUT}s，每 {POLL_INTERVAL}s 一轮）")
    start = time.monotonic()
    deadline = start + VERIFY_TIMEOUT
    rounds = 0
    last_doc, last_doc_err = None, None
    last_results = {}
    prev_stat = object()
    while time.monotonic() < deadline:
        rounds += 1
        last_doc, last_doc_err = get_document(api_key, kb_id, doc_id)
        if last_doc:
            fail_info = last_doc.get("failInfo") or {}
            emb_code = fail_info.get("embedding_code")
            if emb_code not in (None, 0, "0"):
                raise KBError("文档处理明确失败，无需再等：向量化失败 embedding_code="
                              f"{emb_code}，embedding_msg={fail_info.get('embedding_msg')!r}；"
                              f"文档状态：{trunc_json(last_doc)}")
            stat = last_doc.get("embedding_stat")
            if stat != prev_stat:
                # embedding_stat 的枚举值官方文档未公布，这里原样展示、仅供参考
                log(f"文档状态：embedding_stat={stat}，word_num={last_doc.get('word_num')}，"
                    f"length={last_doc.get('length')}")
                prev_stat = stat
        for query in queries:
            results = retrieve(api_key, kb_id, query)
            last_results[query] = results
            hit = find_verified_hit(results, doc_id, file_name, faq_no_ws)
            if hit is not None:
                return {"verified": True, "query": query, "hit": hit,
                        "elapsed": time.monotonic() - start, "rounds": rounds}
        if rounds == 1:
            log("第 1 轮检索未命中——刚上传的文档需要异步解析/构建向量索引，属正常现象，继续等待…")
        time.sleep(POLL_INTERVAL)
    return {"verified": False, "rounds": rounds, "waited": VERIFY_TIMEOUT,
            "last_doc": last_doc, "last_doc_err": last_doc_err, "last_results": last_results}


# ---------------------- 失败时的诊断输出 ----------------------
def print_failure_diagnostics(api_key, kb_id, result):
    print("\n" + "─" * 62)
    print("诊断信息（用于判断为什么检索不到）：")
    kb = describe_knowledge_base(api_key, kb_id)
    if kb:
        print(f"  知识库：document_size={kb.get('document_size')}，word_num={kb.get('word_num')}，"
              f"length={kb.get('length')}（word_num=0 通常说明文档没解析出内容）")
    doc, doc_err = result.get("last_doc"), result.get("last_doc_err")
    if doc:
        print(f"  文档最后状态：name={doc.get('name')!r}，word_num={doc.get('word_num')}，"
              f"length={doc.get('length')}，embedding_stat={doc.get('embedding_stat')}，"
              f"failInfo={doc.get('failInfo')}")
    if doc_err:
        print(f"  文档状态查询异常：{doc_err}")
    for query, results in (result.get("last_results") or {}).items():
        if results:
            top = results[0] if isinstance(results[0], dict) else {}
            meta = top.get("metadata") or {}
            snippet = " ".join(str(top.get("text") or "").split())[:80]
            print(f"  检索 {query!r} → 返回 {len(results)} 条，但未能认定是 faq.txt 的内容："
                  f"top score={top.get('score')}，doc_id={meta.get('doc_id')}，"
                  f"doc_name={meta.get('doc_name')!r}，片段：{snippet!r}")
        else:
            print(f"  检索 {query!r} → 返回 0 条（空结果：向量索引还没建好，或内容没被切出来）")
    print("─" * 62)


def print_failure_hints():
    print(
        "\n可能的原因（参考官方文档与知识库 FAQ，按概率排序）：\n"
        f"  1. 文档仍在异步解析/构建向量索引（排队或内容较多），本次 {VERIFY_TIMEOUT}s 等待不够——"
        "可调大脚本顶部的 VERIFY_TIMEOUT 后重跑；\n"
        "  2. 文档没解析出有效内容（上方诊断里 word_num=0）：文件内容/切片方式导致切片为空；\n"
        "  3. 账号欠费或该 API Key 无知识库权限（看上方具体报错码与 message）；\n"
        "  4. 平台接口行为有变化：把上方诊断信息与 docs.bigmodel.cn 的最新文档核对。\n"
        "注：本次创建的知识库已按约定删除；排查时可重跑脚本（会重新建库并输出诊断）。"
    )


def cleanup(api_key, kb_id):
    try:
        delete_knowledge_base(api_key, kb_id)
        log(f"清理完成：知识库 {kb_id} 已删除。")
        return True
    except KBError as exc:
        print(f"[警告] 知识库清理失败：{exc}", file=sys.stderr, flush=True)
        print(f"[警告] 请尽快到智谱开放平台控制台（bigmodel.cn → 知识库）手动删除知识库 "
              f"{kb_id}，避免残留资源。", file=sys.stderr, flush=True)
        return False


# ---------------------- 本地准备 ----------------------
def load_api_key():
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    if not api_key:
        raise KBError('环境变量 ZHIPUAI_API_KEY 未设置（或为空）。请先执行：'
                      'export ZHIPUAI_API_KEY="你的API Key"')
    return api_key


def _decode_text(raw):
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_faq():
    """在脚本所在目录（其次当前工作目录）找 faq.txt。返回 (路径, 原始字节, 文本)。"""
    candidates = [Path(__file__).resolve().parent / FAQ_NAME, Path.cwd() / FAQ_NAME]
    for path in candidates:
        if path.is_file():
            raw = path.read_bytes()
            return path, raw, _decode_text(raw)
    tried = " 或 ".join(str(p) for p in candidates)
    raise KBError(f"找不到 {FAQ_NAME}（尝试过：{tried}）。请把 faq.txt 放到脚本同目录后再运行。")


_LEADING_MARKS_RE = re.compile(r"^[\d\s#\*\.、,，:：\-—【】\[\]()（）]+")
_QA_PREFIX_RE = re.compile(r"^[QqAa]\s*\d*\s*[\.、:：\-\s]*")


def _clean_query(line):
    """去掉行首的题号/项目符号（如 "12."、"Q3:"、"问:"），留下真正的问题内容。"""
    q = _LEADING_MARKS_RE.sub("", line.strip())
    q = _QA_PREFIX_RE.sub("", q).strip()
    return q if len(q) >= 6 else line.strip()


def build_queries(faq_text, max_queries=3):
    """从 faq.txt 里挑最多 3 条有区分度的真实查询词（优先问句，取首/中/尾）。"""
    lines = [ln.strip() for ln in faq_text.splitlines() if len(ln.strip()) >= 6]
    pool = [ln for ln in lines if ("?" in ln or "？" in ln)] or lines
    if len(pool) >= max_queries:
        positions = sorted({0, len(pool) // 2, len(pool) - 1})[:max_queries]
    else:
        positions = list(range(len(pool)))
    queries = []
    for pos in positions:
        q = _clean_query(pool[pos])[:60].strip()
        if len(q) >= 4 and q not in queries:
            queries.append(q)
    if not queries:  # 内容实在太少的兜底
        compact = "".join(faq_text.split())[:20]
        queries = [compact or "faq"]
    return queries


# ---------------------- 主流程 ----------------------
def main():
    print("=" * 62)
    print("智谱托管知识库灌入 + 真实检索校验（结束时自动删除知识库）")
    print("=" * 62)
    try:
        api_key = load_api_key()
        faq_path, faq_bytes, faq_text = load_faq()
    except KBError as exc:
        print(f"【失败】{exc}")
        return 1

    line_count = len([ln for ln in faq_text.splitlines() if ln.strip()])
    log(f"API Key：{api_key[:8]}…；文档：{faq_path}（非空行 {line_count} 行，{len(faq_bytes)} 字节）")

    faq_no_ws = "".join(faq_text.split())
    queries = build_queries(faq_text)
    log(f"检索验证用的查询词（取自 faq.txt 本身）：{queries}")

    kb_id = None
    verified = False
    failure = None

    try:
        # 步骤 1：建库
        kb_name = f"faq-verify-{time.strftime('%Y%m%d-%H%M%S')}"
        kb_id = create_knowledge_base(
            api_key, kb_name, "main.py 临时创建：验证 faq.txt 可检索，脚本结束自动删除")
        log(f"步骤 1/4 创建知识库成功：kb_id={kb_id}（embedding_id={EMBEDDING_ID}）")

        # 步骤 2：上传文档
        doc_id = upload_document(api_key, kb_id, faq_path.name, faq_bytes)
        log(f"步骤 2/4 文档上传成功：documentId={doc_id}")
        log("注意：上传成功 ≠ 可检索（解析/向量化是异步的），必须通过下面的真实检索验证")

        # 步骤 3：检索验证（核心门槛）
        result = wait_until_retrievable(api_key, kb_id, doc_id, faq_path.name, queries, faq_no_ws)
        if result["verified"]:
            verified = True
            hit = result["hit"]
            meta = hit.get("metadata") or {}
            snippet = " ".join(str(hit.get("text") or "").split())[:100]
            log(f"步骤 3/4 检索验证通过（第 {result['rounds']} 轮，用时 {result['elapsed']:.0f}s）：")
            log(f"        query = {result['query']!r}")
            log(f"        命中切片 score={hit.get('score')}，doc_id={meta.get('doc_id')}，"
                f"doc_name={meta.get('doc_name')!r}")
            log(f"        片段：{snippet!r}")
        else:
            failure = (f"检索验证未通过：等了 {result['waited']}s、重试 {result['rounds']} 轮，"
                       f"用 {len(queries)} 个来自 faq.txt 的查询词都没能从知识库召回 faq.txt 的内容。")
            print_failure_diagnostics(api_key, kb_id, result)
            print_failure_hints()

        # 步骤 4：清理
        log("步骤 4/4 清理知识库")
    except KBError as exc:
        failure = str(exc)
    except KeyboardInterrupt:
        failure = "脚本被手动中断（Ctrl+C）"
    finally:
        if kb_id:  # 无论成功失败都要清理
            cleanup(api_key, kb_id)

    print("\n" + "=" * 62)
    if verified:
        print(f"【成功】faq.txt 已灌入智谱知识库，且真实检索验证通过（kb={kb_id}，已清理）。")
        print("=" * 62)
        return 0
    print(f"【失败】{failure}")
    print("详见上方诊断信息与原因分析；知识库清理结果见上方日志。")
    print("=" * 62)
    return 1


if __name__ == "__main__":
    sys.exit(main())
