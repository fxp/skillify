#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱（BigModel）托管知识库，并在清理前验证它真的能被检索到。

流程：创建知识库 -> 上传 faq.txt -> 轮询文档解析 -> 真刀真枪调检索接口校验 -> 无论成败删除知识库。

关键点：上传接口返回"成功"只代表文件收下了，官方 FAQ 明确说"只有状态变为
「处理完成」后才可以正常检索"。所以本脚本在宣告成功之前，必须用知识库检索
接口实际召回 faq.txt 的内容（doc_id 对得上、或内容与原文有 >=12 字连续重叠），
否则算失败，并把原因讲清楚，不报喜不报忧。

依赖：仅 requests。用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import difflib
import os
import sys
import time
import uuid
from pathlib import Path

import requests

API_BASE = "https://open.bigmodel.cn/api/llm-application/open"
DOC_TIMEOUT = int(os.environ.get("KB_DOC_TIMEOUT", "300"))        # 等文档解析的最长秒数
VERIFY_TIMEOUT = int(os.environ.get("KB_VERIFY_TIMEOUT", "300"))  # 等检索可用的最长秒数
POLL_INTERVAL = 5


class FatalError(RuntimeError):
    """流程失败；str(e) 就是要展示给用户的原因。"""

    def __init__(self, message, http_status=None):
        super().__init__(message)
        self.http_status = http_status


def log(message):
    print(message, flush=True)


def request_json(session, headers, method, url, retries=3, **kwargs):
    """统一请求封装：网络/5xx 自动重试；HTTP 与业务 code 任一不为 200 即抛 FatalError。"""
    last_error = None
    for attempt in range(1, retries + 1):
        resp = None
        try:
            resp = session.request(method, url, timeout=(10, 120), headers=headers, **kwargs)
        except requests.RequestException as exc:
            last_error = f"网络异常：{exc!r}"
        if resp is not None and resp.status_code >= 500 and attempt < retries:
            last_error = f"服务端错误 HTTP {resp.status_code}"
            resp = None
        if resp is None:
            if attempt < retries:
                log(f"  {method} {url}：{last_error}（第 {attempt}/{retries} 次），{POLL_INTERVAL}s 后重试")
                time.sleep(POLL_INTERVAL)
                continue
            break
        try:
            body = resp.json()
        except ValueError:
            raise FatalError(
                f"{method} {url} 返回的不是 JSON（HTTP {resp.status_code}）：{resp.text[:300]}",
                resp.status_code,
            )
        if resp.status_code != 200 or body.get("code", 200) not in (200, 0):
            raise FatalError(
                f"{method} {url} 失败：HTTP {resp.status_code}，响应：{body}",
                resp.status_code,
            )
        return body
    raise FatalError(f"{method} {url} 重试 {retries} 次仍失败，最后错误：{last_error}")


def read_faq(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FatalError(f"{path} 既不是 UTF-8 也不是 GBK 编码，请先转成 UTF-8 再运行")


def create_knowledge(session, headers):
    name = f"faq-verify-{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    body = request_json(session, headers, "POST", f"{API_BASE}/knowledge", json={
        "name": name,
        "description": "faq.txt 自动灌库校验，脚本结束即删除",
        "embedding_id": 11,           # 11 = Embedding-3
        "embedding_model": "Embedding-3",
    })
    kb_id = (body.get("data") or {}).get("id")
    if not kb_id:
        raise FatalError(f"创建知识库响应里没有 data.id：{body}")
    log(f"[1/5] 知识库创建成功：{name}（id={kb_id}）")
    return name, kb_id


def upload_document(session, headers, kb_id, faq_path):
    with faq_path.open("rb") as fh:
        body = request_json(
            session, headers, "POST",
            f"{API_BASE}/document/upload_document/{kb_id}",
            files={"files": (faq_path.name, fh, "text/plain")},  # 表单字段名是 files
            data={"knowledge_type": "1", "parse_image": "false"},
        )
    info = body.get("data") or {}
    failed = info.get("failedInfos") or []
    if failed:
        reason = "；".join(
            f"{item.get('fileName')}: {item.get('failReason')}" for item in failed)
        raise FatalError(f"服务端拒绝了文档上传：{reason}")
    success = info.get("successInfos") or []
    if not success:
        raise FatalError(f"上传响应里既没有成功也没有失败记录：{body}")
    doc_id = success[0].get("documentId")
    if not doc_id:
        raise FatalError(f"上传成功记录里缺少 documentId：{body}")
    log(f"[2/5] 文档上传成功：{success[0].get('fileName')}（documentId={doc_id}）")
    return doc_id


def wait_document_ready(session, headers, doc_id):
    """轮询文档详情：解析出正文字数（word_num>0）才算解析完成；failInfo 有内容直接报错。"""
    url = f"{API_BASE}/document/{doc_id}"
    deadline = time.monotonic() + DOC_TIMEOUT
    while time.monotonic() < deadline:
        detail = (request_json(session, headers, "GET", url).get("data") or {})
        fail = detail.get("failInfo") or {}
        if fail.get("embedding_msg") or fail.get("embedding_code"):
            raise FatalError(
                "文档向量化失败："
                f"embedding_code={fail.get('embedding_code')}，"
                f"embedding_msg={fail.get('embedding_msg')}")
        word_num = detail.get("word_num") or 0
        log(f"  解析中：embedding_stat={detail.get('embedding_stat')}，word_num={word_num}")
        if word_num > 0:
            log(f"[3/5] 文档解析完成：共 {word_num} 字")
            return
        time.sleep(POLL_INTERVAL)
    raise FatalError(
        f"等了 {DOC_TIMEOUT}s 文档仍未解析完成（word_num 一直是 0），"
        "知识库尚不可用，不再往下验证")


def pick_queries(faq_text):
    """从 faq.txt 原文里挑几条有代表性的句子当检索词（原句检索最稳，不依赖分词）。"""
    lines = [line.strip() for line in faq_text.splitlines() if len(line.strip()) >= 8]
    if not lines:
        return [faq_text.strip()[:60] or "常见问题"]
    candidates = [lines[0], max(lines, key=len), lines[len(lines) // 2]]
    queries, seen = [], set()
    for query in candidates:
        query = query[:60]
        if query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def from_our_document(result, doc_id, norm_source):
    """判断一条检索结果是否确实来自刚上传的 faq.txt：看 doc_id，或看内容与原文是否重叠。"""
    metadata = result.get("metadata") or {}
    if metadata.get("doc_id") == doc_id:
        return True
    text = "".join((result.get("text") or "").split())
    if text:
        match = difflib.SequenceMatcher(
            None, norm_source, text, autojunk=False
        ).find_longest_match(0, len(norm_source), 0, len(text))
        if match.size >= 12:
            return True
    return False


def verify_retrievable(session, headers, kb_id, doc_id, faq_text):
    """核心校验：实际调用检索接口，只有召回了 faq.txt 的内容才算通过。"""
    url = f"{API_BASE}/knowledge/retrieve"
    queries = pick_queries(faq_text)
    norm_source = "".join(faq_text.split())
    deadline = time.monotonic() + VERIFY_TIMEOUT
    round_no = 0
    last_error = None
    while time.monotonic() < deadline:
        round_no += 1
        for query in queries:
            try:
                body = request_json(session, headers, "POST", url, json={
                    "query": query,
                    "knowledge_ids": [kb_id],
                    "top_k": 5,
                })
            except FatalError as exc:
                if exc.http_status in (401, 403):  # 鉴权问题，重试无意义
                    raise
                last_error = str(exc)
                continue
            results = body.get("data") or []
            if not results:
                last_error = f"query={query!r} 召回 0 条"
                continue
            proven = [item for item in results
                      if from_our_document(item, doc_id, norm_source)]
            if not proven:
                names = [((item.get("metadata") or {}).get("doc_name"),
                          (item.get("metadata") or {}).get("doc_id"))
                         for item in results]
                last_error = f"有召回结果但都不是刚上传的文档：{names}"
                continue
            best = max(proven, key=lambda item: item.get("score") or 0)
            snippet = (best.get("text") or "").strip().replace("\n", " ")
            log(f"[4/5] 检索验证通过：query={query!r} 召回 {len(results)} 条，"
                f"其中 {len(proven)} 条确认来自 faq.txt")
            log(f"      最高分 score={best.get('score')}，内容片段：{snippet[:80]}…")
            return
        log(f"  第 {round_no} 轮检索未命中（{last_error}），{POLL_INTERVAL}s 后重试…")
        time.sleep(POLL_INTERVAL)
    raise FatalError(
        f"检索验证失败：上传和解析都显示成功，但 {VERIFY_TIMEOUT}s 内始终无法从"
        f"知识库检索到 faq.txt 的内容（最后状态：{last_error}）。知识库实际不可用，"
        "不能算成功（知识库将被清理）")


def delete_knowledge(session, headers, kb_id, name):
    try:
        request_json(session, headers, "DELETE", f"{API_BASE}/knowledge/{kb_id}")
        log(f"[5/5] 清理完成：知识库 {name}（id={kb_id}）已删除")
    except FatalError as exc:
        log(f"[警告] 知识库删除失败，请到 bigmodel.cn 控制台手动删除"
            f"（id={kb_id}）：{exc}")


def main():
    log("=" * 62)
    log("智谱托管知识库灌库：建库 -> 上传 -> 解析 -> 检索验证 -> 清理")
    log("=" * 62)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        log("[失败] 请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")
        return 1

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    if not faq_path.is_file():
        log(f"[失败] 找不到 {faq_path}，请把 faq.txt 放在脚本同目录下")
        return 1
    try:
        faq_text = read_faq(faq_path)
    except FatalError as exc:
        log(f"[失败] {exc}")
        return 1
    if not faq_text.strip():
        log(f"[失败] {faq_path} 是空文件，没有可上传的内容")
        return 1
    log(f"准备上传：{faq_path}（{len(faq_text)} 字符，{len(faq_text.splitlines())} 行）")

    session = requests.Session()
    headers = {"Authorization": f"Bearer {api_key}"}
    kb_name = None
    kb_id = None
    try:
        kb_name, kb_id = create_knowledge(session, headers)
        doc_id = upload_document(session, headers, kb_id, faq_path)
        wait_document_ready(session, headers, doc_id)
        verify_retrievable(session, headers, kb_id, doc_id, faq_text)
        log("=" * 62)
        log("成功：faq.txt 已灌入知识库，且真实检索验证通过（见下方清理记录）。")
        log("=" * 62)
        return 0
    except FatalError as exc:
        log("=" * 62)
        log(f"[失败] {exc}")
        log("=" * 62)
        return 1
    except requests.RequestException as exc:
        log(f"[失败] 网络请求异常：{exc!r}")
        return 1
    finally:
        if kb_id:
            delete_knowledge(session, headers, kb_id, kb_name)


if __name__ == "__main__":
    sys.exit(main())
