#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱（BigModel）托管知识库，并做"真的能检索到"的校验。

流程：
  1. 创建知识库（Embedding-3 向量化模型）
  2. 上传 faq.txt
  3. 轮询文档解析/向量化状态（failInfo 有内容则立刻带原因报错）
  4. 【关键校验】调用知识库检索接口，用从 faq.txt 内容里提炼的查询词做真实检索，
     并核对召回切片确实来自 faq.txt 原文（避免"接口通了但内容查不到"的假成功）；
     状态轮询超时也不轻信，仍以检索结果为准
  5. 无论成功失败，最后清理：删文档、删知识库

API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖第三方库 requests。
退出码：0 = 上传成功且检索校验通过且清理完成；1 = 任一环节失败。
"""

import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
API_KEY_ENV = "ZHIPUAI_API_KEY"
FAQ_FILE = Path(__file__).resolve().parent / "faq.txt"

KB_CREATE_PATH = "/llm-application/open/knowledge"
KB_DELETE_PATH = "/llm-application/open/knowledge/{kb_id}"
DOC_UPLOAD_PATH = "/llm-application/open/document/upload_document/{kb_id}"
DOC_DETAIL_PATH = "/llm-application/open/document/{doc_id}"
DOC_DELETE_PATH = "/llm-application/open/document/{doc_id}"
RETRIEVE_PATH = "/llm-application/open/knowledge/retrieve"

EMBEDDING_MODEL_ID = 11      # 11 = Embedding-3（3=Embedding-2, 12=Embedding-3-pro）
EMBEDDING_MODEL_NAME = "Embedding-3"

REQUEST_TIMEOUT = (10, 120)  # (连接超时, 读超时)，秒
PARSE_TIMEOUT = 300          # 等文档解析+向量化的最长时间，秒
PARSE_POLL_INTERVAL = 5
RETRIEVE_WINDOW = 120        # 状态完成后，检索校验的重试窗口，秒（索引可能略有滞后）
RETRIEVE_RETRY_INTERVAL = 10

# embedding_stat 官方文档未枚举取值；按接口示例（embedding_stat=0 且带 failInfo=失败）
# 与控制台状态口径处理：1 = 处理完成；failInfo 非空 = 失败；其余 = 处理中。
# 即便判断口径有偏差，最终成败仍以第 4 步真实检索为准，不会误报成功。
EMBEDDING_STAT_DONE = 1

SESSION = requests.Session()


class KBError(Exception):
    """知识库流程错误（已带可读原因）。"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- HTTP 封装

def _api(method: str, path: str, *, params=None, json_body=None, files=None) -> dict:
    url = BASE_URL + path
    try:
        resp = SESSION.request(
            method, url, params=params, json=json_body, files=files,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KBError(f"请求 {method} {url} 失败（网络异常）：{exc}") from exc
    if resp.status_code != 200:
        raise KBError(f"{method} {url} 返回 HTTP {resp.status_code}，响应片段：{resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise KBError(f"{method} {url} 返回的不是 JSON，响应片段：{resp.text[:300]}") from exc
    # 智谱知识库接口信封：{"code": 200, "message": ..., "data": ...}
    if payload.get("code") != 200:
        raise KBError(
            f"{method} {url} 业务失败：code={payload.get('code')} "
            f"message={payload.get('message')!r}"
        )
    return payload


# ---------------------------------------------------------------- 各环节

def create_knowledge_base() -> str:
    name = f"faq-upload-verify-{time.strftime('%Y%m%d%H%M%S')}"
    payload = _api("POST", KB_CREATE_PATH, json_body={
        "embedding_id": EMBEDDING_MODEL_ID,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "contextual": 0,  # 不开上下文增强：更快，且校验只看切片原文
        "name": name,
        "description": "临时知识库：faq.txt 上传与检索可用性校验，跑完即删",
    })
    kb_id = (payload.get("data") or {}).get("id")
    if not kb_id:
        raise KBError(f"创建知识库成功但响应里没有 data.id，原始响应：{payload}")
    log(f"知识库创建成功：id={kb_id}（name={name}，向量化模型 {EMBEDDING_MODEL_NAME}）")
    return kb_id


def upload_document(kb_id: str) -> list:
    with FAQ_FILE.open("rb") as fh:
        payload = _api("POST", DOC_UPLOAD_PATH.format(kb_id=kb_id), files={
            # 接口要求 multipart 字段名为 files；knowledge_type 不传由服务端动态解析
            "files": (FAQ_FILE.name, fh, "text/plain"),
        })
    data = payload.get("data") or {}
    failed = data.get("failedInfos") or []
    if failed:
        reasons = "；".join(
            f"{item.get('fileName')}: {item.get('failReason')}" for item in failed
        )
        raise KBError(f"文档上传被服务端拒绝：{reasons}")
    success = data.get("successInfos") or []
    doc_ids = [item.get("documentId") for item in success]
    if not doc_ids or any(not d for d in doc_ids):
        raise KBError(f"上传响应缺少 documentId，原始响应：{payload}")
    log(f"faq.txt 上传成功：documentId={doc_ids}")
    return doc_ids


def get_doc_detail(doc_id: str) -> dict:
    return _api("GET", DOC_DETAIL_PATH.format(doc_id=doc_id)).get("data") or {}


def wait_documents_ready(doc_ids: list):
    """轮询文档状态。返回 (是否就绪, 说明)。

    - failInfo 非空：向量化失败，立即返回失败并带官方原因；
    - embedding_stat == 1：视为处理完成；
    - 超时：返回失败说明（主流程仍会继续做真实检索校验，不轻信状态）。
    """
    deadline = time.time() + PARSE_TIMEOUT
    last_stat = {}
    while time.time() < deadline:
        pending = []
        for doc_id in doc_ids:
            detail = get_doc_detail(doc_id)
            stat = detail.get("embedding_stat")
            last_stat[doc_id] = stat
            fail = detail.get("failInfo") or {}
            if fail.get("embedding_msg") or fail.get("embedding_code") not in (None, 0):
                return False, (
                    f"文档向量化失败（failInfo）：code={fail.get('embedding_code')} "
                    f"msg={fail.get('embedding_msg')}"
                )
            if stat != EMBEDDING_STAT_DONE:
                pending.append(f"{detail.get('name') or doc_id}(embedding_stat={stat})")
        if not pending:
            return True, "全部文档处理完成（embedding_stat=1）"
        log(f"文档仍在解析/向量化中：{', '.join(pending)}，{PARSE_POLL_INTERVAL}s 后重查")
        time.sleep(PARSE_POLL_INTERVAL)
    return False, (
        f"等待 {PARSE_TIMEOUT}s 后文档仍未标记完成，最后 embedding_stat={last_stat}；"
        "不直接判死，继续用真实检索校验"
    )


# ---------------------------------------------------------------- 检索校验

def build_queries(faq_text: str) -> list:
    """从 faq.txt 原文提炼检索用查询词（问题行优先、长行优先）。

    返回 [(query, recall_method), ...]：前几条用混合检索，最后加一条关键词检索兜底
    （关键词检索与原文精确匹配，最能证明内容真的入库了）。
    """
    lines = [ln.strip() for ln in faq_text.splitlines() if ln.strip()]
    cands = []
    for ln in lines:
        q = re.sub(
            r"^(Q\s*[:.、．]?\s*|问\s*[:：]\s*|\d+\s*[.、:：]\s*)", "", ln,
            flags=re.IGNORECASE,
        ).strip()
        if len(q) >= 6:
            is_question = ("?" in q) or ("？" in q)
            cands.append((not is_question, -len(q), q))  # 问题行优先，其次更长的行
    cands.sort()
    picked, seen = [], set()
    for _, _, q in cands:
        key = q[:20]
        if key in seen:
            continue
        seen.add(key)
        picked.append(q[:40])
        if len(picked) == 3:
            break
    if not picked:
        raise KBError("无法从 faq.txt 中提炼出可用的检索查询词（有效行太少）")
    queries = [(q, "mixed") for q in picked]
    queries.append((picked[0], "keyword"))
    return queries


def text_from_faq(chunk: str, faq_text: str, window: int = 10) -> bool:
    """判断召回切片是否真出自 faq.txt：存在 window 字以上连续原文重叠。"""
    compact = re.sub(r"\s+", "", chunk or "")
    if not compact:
        return False
    if len(compact) < window:
        return compact in faq_text
    for i in range(len(compact) - window + 1):
        if compact[i:i + window] in faq_text:
            return True
    return False


def verify_retrieval(kb_id: str, queries: list, faq_text: str):
    """真实检索校验：有查询命中切片、且切片内容确来自 faq.txt 才算通过。"""
    deadline = time.time() + RETRIEVE_WINDOW
    attempt = 0
    last_summary = "尚未发起检索"
    while time.time() < deadline:
        attempt += 1
        for query, method in queries:
            try:
                payload = _api("POST", RETRIEVE_PATH, json_body={
                    "query": query,
                    "knowledge_ids": [kb_id],
                    "top_k": 5,
                    "recall_method": method,
                })
            except KBError as exc:
                last_summary = f"检索请求失败：{exc}"
                log(last_summary)
                continue
            chunks = payload.get("data") or []
            if not chunks:
                last_summary = f"查询 {query!r}（{method}）召回 0 条切片"
                continue
            for chunk in chunks:
                text = chunk.get("text") or ""
                if text_from_faq(text, faq_text):
                    snippet = re.sub(r"\s+", " ", text)[:80]
                    return True, (
                        f"第 {attempt} 轮：查询 {query!r}（{method} 检索）召回 "
                        f"{len(chunks)} 条切片，最高分 score={chunk.get('score')}，"
                        f"且切片内容与 faq.txt 原文逐字匹配：\n    “{snippet}……”"
                    )
            last_summary = (
                f"查询 {query!r}（{method}）召回 {len(chunks)} 条，"
                "但切片与 faq.txt 原文无 10 字以上连续重叠（内容可疑）"
            )
        log(f"第 {attempt} 轮检索校验未通过（{last_summary}），{RETRIEVE_RETRY_INTERVAL}s 后重试")
        time.sleep(RETRIEVE_RETRY_INTERVAL)
    return False, (
        f"在 {RETRIEVE_WINDOW}s 内共 {attempt} 轮检索均未命中可验证内容。最后情况：{last_summary}。"
        "常见原因：① 文档仍在解析/索引构建中（官方口径：数据处理中→索引构建中→处理完成，"
        "完成后才可检索，大文件更久）；② 向量化失败（字数超限、内容为空、账户额度不足）；"
        "③ 文件编码或切片方式导致内容未被正确解析。"
    )


# ---------------------------------------------------------------- 清理

def cleanup(kb_id, doc_ids) -> bool:
    """无论成败都清理；知识库删除失败时明确告知用户手动处理。"""
    for doc_id in doc_ids or []:
        try:
            _api("DELETE", DOC_DELETE_PATH.format(doc_id=doc_id))
            log(f"文档已删除：{doc_id}")
        except KBError as exc:
            log(f"删除文档 {doc_id} 失败（不影响删库，稍后随库一并清理）：{exc}")
    if not kb_id:
        log("知识库未创建成功，无需清理")
        return True
    try:
        _api("DELETE", KB_DELETE_PATH.format(kb_id=kb_id))
        log(f"知识库已删除：{kb_id}，清理完成")
        return True
    except KBError as exc:
        print(
            f"错误：知识库删除失败！请到智谱开放平台控制台手动删除，知识库ID={kb_id}。原因：{exc}",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------- 主流程

def read_faq() -> str:
    if not FAQ_FILE.is_file():
        raise KBError(f"未找到 {FAQ_FILE}（脚本读取与自身同目录的 faq.txt）")
    raw = FAQ_FILE.read_bytes()
    if not raw.strip():
        raise KBError(f"{FAQ_FILE} 是空文件，没有可上传的内容")
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise KBError(f"{FAQ_FILE} 编码无法识别（已尝试 utf-8 / gbk），请另存为 UTF-8 后重试")


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"错误：未设置环境变量 {API_KEY_ENV}。请先执行 export {API_KEY_ENV}=<你的智谱API Key> 再运行。", file=sys.stderr)
        return 1
    SESSION.headers.update({
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "faq-kb-upload-verify/1.0",
    })
    try:
        faq_text = read_faq()
    except KBError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    kb_id, doc_ids, exit_code = None, [], 1
    try:
        log(f"读取 faq.txt 成功：{len(faq_text)} 字符 / {faq_text.count(chr(10)) + 1} 行")
        kb_id = create_knowledge_base()
        doc_ids = upload_document(kb_id)

        ready, reason = wait_documents_ready(doc_ids)
        if ready:
            log(reason)
        elif "failInfo" in reason:
            # 服务端已明确说向量化失败：直接带原因报错，不再浪费检索
            raise KBError(f"文档处理失败，无法进入检索校验。原因：{reason}")
        else:
            log(f"警告：{reason}")

        queries = build_queries(faq_text)
        log(f"检索校验查询（取自 faq.txt 原文）：{[q for q, _ in queries]}")
        ok, detail = verify_retrieval(kb_id, queries, faq_text)
        if ok:
            log(f"检索校验通过 ✅ {detail}")
            print("\n结论：faq.txt 已成功入库，且内容可被真实检索到（切片与原文逐字比对通过）。")
            exit_code = 0
        else:
            log(f"检索校验失败 ❌ {detail}")
            print(
                "\n结论：上传接口虽返回成功，但文档当前无法被检索到——本次判定为失败，不做任何“报喜不报忧”。",
                file=sys.stderr,
            )
    except KBError as exc:
        print(f"\n流程失败：{exc}", file=sys.stderr)
    finally:
        if not cleanup(kb_id, doc_ids) and exit_code == 0:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
