#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把同目录下的 faq.txt 灌进智谱（bigmodel.cn）托管知识库，并校验"真的能检索到"。

用法:
    ZHIPUAI_API_KEY=你的key python3 main.py

流程:
    ① 创建临时知识库（Embedding-3）
    ② 上传 faq.txt（multipart 字段名 files，knowledge_type=1 标题/段落切片）
    ③ 轮询文档详情，等向量化走完「数据处理中 → 索引构建中 → 处理完成」
    ④ 【核心校验】调用知识库检索接口、且限定 document_ids 只查这份文档，
       必须真实召回非空分片才算成功。"上传接口返回成功"本身不算数。
    ⑤ 无论成功失败，最后删除临时知识库。

退出码: 0 = 全流程成功（含清理）; 1 = 流程失败; 2 = 流程成功但清理失败

接口依据（docs.bigmodel.cn 官方文档「知识库 API」）:
    POST   /api/llm-application/open/knowledge                         创建知识库
    POST   /api/llm-application/open/document/upload_document/{kb_id}  上传文件文档
    GET    /api/llm-application/open/document/{doc_id}                 文档详情(embedding_stat)
    POST   /api/llm-application/open/knowledge/retrieve                知识库检索
    DELETE /api/llm-application/open/knowledge/{kb_id}                 删除知识库
"""

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/llm-application/open"
EMBEDDING_ID = 11  # 创建知识库绑定的向量化模型: 11=Embedding-3 (3=Embedding-2, 12=Embedding-3-pro)

# 官方 FAQ 只给了状态流转「数据处理中→索引构建中→处理完成(另有 数据异常)」，
# 没给数值表；0/1/2/3 是按该顺序对应的常见取值。未知值会原样打印，且不影响成败判定
# ——成败最终以第④步真实检索为准。
EMBEDDING_STAT_LABELS = {0: "数据处理中", 1: "索引构建中", 2: "处理完成", 3: "数据异常"}
STAT_READY = 2
STAT_BROKEN = 3

DOC_WAIT_TIMEOUT = 300    # 等向量化完成的最长时间（秒）
DOC_POLL_INTERVAL = 5
RETRIEVE_ATTEMPTS = 6     # 检索校验最多尝试次数
RETRIEVE_INTERVAL = 10
HTTP_TIMEOUT = (10, 60)   # (连接超时, 读取超时)

FAQ_FILE = Path(__file__).resolve().parent / "faq.txt"
KB_NAME_PREFIX = "faq-upload-check-"

API_KEY = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()


class KBError(RuntimeError):
    """业务失败，message 已带上可读的接口错误信息。"""

    def __init__(self, step, message, code=None):
        self.code = code
        text = f"[{step}] {message}"
        if code is not None:
            text += f"（code={code}）"
        super().__init__(text)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _err_detail(resp, body):
    if isinstance(body, dict):
        return str(body.get("message") or body)
    text = (resp.text or "").strip()
    return f"非 JSON 响应: {text[:200]}"


def api_call(step, method, path, **kwargs):
    """统一请求封装：Bearer 鉴权、429/5xx/1302 自动重试、错误归一化为 KBError。

    成功条件：HTTP 200 且响应体 code == 200（该接口族以 body.code 表示业务结果）。
    """
    url = BASE_URL + path
    headers = {"Authorization": f"Bearer {API_KEY}"}
    for attempt in range(1, 4):
        try:
            resp = requests.request(method, url, headers=headers, timeout=HTTP_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise KBError(step, f"网络请求异常: {type(e).__name__}: {e}") from e
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code == 200 and isinstance(body, dict) and body.get("code") == 200:
            return body
        retriable = resp.status_code in (429, 500, 502, 503, 504) or (
            isinstance(body, dict) and str(body.get("code")) == "1302")
        if retriable and attempt < 3:
            log(f"{step} 暂时失败（{_err_detail(resp, body)}），{attempt * 2}s 后重试...")
            time.sleep(attempt * 2)
            continue
        code = body.get("code") if isinstance(body, dict) else resp.status_code
        raise KBError(step, f"接口失败 HTTP {resp.status_code}: {_err_detail(resp, body)}", code)
    raise KBError(step, "重试次数用尽，仍然失败")  # 理论上不可达


def create_knowledge_base(name):
    body = api_call("创建知识库", "POST", "/knowledge", json_body={
        "embedding_id": EMBEDDING_ID,
        "name": name,
        "description": "faq.txt 自动化上传+检索校验用的临时知识库，跑完即删",
    })
    kb_id = (body.get("data") or {}).get("id")
    if not kb_id:
        raise KBError("创建知识库", f"响应中没有 data.id: {body}")
    return str(kb_id)


def upload_document(kb_id, file_path):
    raw = file_path.read_bytes()
    body = api_call(
        "上传文档", "POST", f"/document/upload_document/{kb_id}",
        data={"knowledge_type": "1"},  # 1 = 标题/段落切片（支持 txt）
        files={"files": (file_path.name, raw, "text/plain")},  # 官方 multipart 字段名是 files
    )
    data = body.get("data") or {}
    failed = data.get("failedInfos") or []
    if failed:
        reasons = "; ".join(f"{i.get('fileName')}: {i.get('failReason')}" for i in failed)
        raise KBError("上传文档", f"服务端报告上传失败: {reasons}")
    success = data.get("successInfos") or []
    doc_id = next((i.get("documentId") for i in success if i.get("documentId")), None)
    if not doc_id:
        raise KBError("上传文档", f"接口返回成功但没有拿到 documentId: {body}")
    return str(doc_id)


def get_document(doc_id):
    body = api_call("文档详情", "GET", f"/document/{doc_id}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise KBError("文档详情", f"响应格式异常: {body}")
    return data


def stat_label(stat):
    return EMBEDDING_STAT_LABELS.get(stat, f"未知状态({stat!r})")


def wait_document_ready(doc_id):
    """轮询向量化状态。返回 (是否就绪, 说明)；明确失败直接抛 KBError。"""
    deadline = time.time() + DOC_WAIT_TIMEOUT
    last_stat, err_streak = None, 0
    while time.time() < deadline:
        try:
            doc = get_document(doc_id)
        except KBError as e:
            err_streak += 1
            if err_streak >= 3:
                raise
            log(f"查询文档详情失败（连续第 {err_streak} 次）: {e}，继续重试")
            time.sleep(DOC_POLL_INTERVAL)
            continue
        err_streak = 0
        last_stat = doc.get("embedding_stat")
        fail = doc.get("failInfo") or {}
        if isinstance(fail, dict) and fail.get("embedding_code"):
            raise KBError(
                "等待向量化",
                f"文档向量化失败: {fail.get('embedding_msg')}"
                f"（embedding_code={fail.get('embedding_code')}）",
                fail.get("embedding_code"),
            )
        if last_stat == STAT_BROKEN:
            raise KBError("等待向量化", f"文档状态为「数据异常」: {doc}")
        if last_stat == STAT_READY:
            return True, ""
        log(f"文档状态: {stat_label(last_stat)}，{DOC_POLL_INTERVAL}s 后再查...")
        time.sleep(DOC_POLL_INTERVAL)
    return False, (f"等待 {DOC_WAIT_TIMEOUT}s 仍未到「处理完成」"
                   f"（最后状态: {stat_label(last_stat)}）")


def build_probe_queries(faq_text):
    """从 faq.txt 里挑几个有区分度的 query，优先问题行。"""
    lines = [ln.strip() for ln in faq_text.splitlines() if len(ln.strip()) >= 6]
    questions = [ln for ln in lines if "?" in ln or "？" in ln]
    picked = []
    for pool in (questions, lines):  # 没有问题行就退化用普通行
        if pool:
            picked.append(pool[0])
            if len(pool) >= 3:
                picked.append(pool[len(pool) // 2])
        if len(picked) >= 3:
            break
    out, seen = [], set()
    for q in picked:
        q = q[:120]
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def retrieve_chunks(kb_id, doc_id, query):
    """调用检索接口，限定只召回本篇文档，返回非空分片列表。"""
    body = api_call("检索校验", "POST", "/knowledge/retrieve", json_body={
        "query": query[:1000],
        "knowledge_ids": [kb_id],
        "document_ids": [doc_id],
        "top_k": 5,
        "recall_method": "mixed",
    })
    data = body.get("data") or []
    return [c for c in data if isinstance(c, dict) and (c.get("text") or "").strip()]


def verify_retrievable(kb_id, doc_id, faq_text):
    """成败标准：检索接口真实召回来自本文档的非空分片。返回 (是否通过, 说明)。"""
    probes = build_probe_queries(faq_text)
    if not probes:
        return False, "faq.txt 中找不到可用于检索测试的文本行"
    log(f"探测 query（{len(probes)} 个）: {probes}")
    norm_file = re.sub(r"\s+", "", faq_text)
    last_reason = ""
    for i in range(RETRIEVE_ATTEMPTS):
        query = probes[i % len(probes)]
        try:
            chunks = retrieve_chunks(kb_id, doc_id, query)
        except KBError as e:
            last_reason = f"检索接口调用失败: {e}"
            log(f"第 {i + 1}/{RETRIEVE_ATTEMPTS} 次尝试失败: {last_reason}")
            time.sleep(RETRIEVE_INTERVAL)
            continue
        if chunks:
            def _score(c):
                s = c.get("score")
                return s if isinstance(s, (int, float)) else 0
            best = max(chunks, key=_score)
            text = (best.get("text") or "").strip()
            evidence = (f"query={query!r} 召回 {len(chunks)} 个分片，最高分 {best.get('score')}，"
                        f"分片摘录: {text[:80]!r}")
            if re.sub(r"\s+", "", text) not in norm_file:
                log("提示: 召回分片与 faq.txt 原文不完全一致（可能被拼接了标题等），仅供参考")
            return True, evidence
        last_reason = f"query={query!r} 检索结果为空（接口正常返回但没有任何分片）"
        log(f"第 {i + 1}/{RETRIEVE_ATTEMPTS} 次: {last_reason}，{RETRIEVE_INTERVAL}s 后重试")
        time.sleep(RETRIEVE_INTERVAL)
    return False, last_reason or "所有探测 query 均未召回任何内容"


def delete_knowledge_base(kb_id):
    api_call("清理知识库", "DELETE", f"/knowledge/{kb_id}")


def read_faq_text(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main():
    if not API_KEY:
        print("错误: 请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台的 API Key）", file=sys.stderr)
        return 1
    if not FAQ_FILE.is_file():
        print(f"错误: 找不到 {FAQ_FILE}", file=sys.stderr)
        return 1
    raw = FAQ_FILE.read_bytes()
    if not raw.strip():
        print(f"错误: {FAQ_FILE} 是空文件", file=sys.stderr)
        return 1

    kb_id = None
    ok, cleanup_ok = False, True
    fail_reason, evidence, status_note = "", "", ""

    try:
        kb_name = f"{KB_NAME_PREFIX}{int(time.time())}"
        log(f"① 创建知识库「{kb_name}」...")
        kb_id = create_knowledge_base(kb_name)
        log(f"   知识库 ID: {kb_id}")

        log(f"② 上传文档 {FAQ_FILE.name}（{len(raw)} 字节）...")
        doc_id = upload_document(kb_id, FAQ_FILE)
        log(f"   文档 ID: {doc_id}（接口受理成功，此时还不代表可检索）")

        log("③ 等待解析与向量化完成...")
        ready, status_note = wait_document_ready(doc_id)
        if ready:
            log("   文档状态: 处理完成")
        else:
            log(f"   警告: {status_note}；改用第④步真实检索做最终判定")

        log("④ 检索校验: 确认文档确实能被检索到...")
        ok, msg = verify_retrievable(kb_id, doc_id, read_faq_text(raw))
        if ok:
            evidence = msg
        else:
            fail_reason = msg
    except KBError as e:
        fail_reason = str(e)
    except Exception as e:  # 兜底: 任何异常都要走到清理
        fail_reason = f"未预期的异常: {type(e).__name__}: {e}"
    finally:
        if kb_id:
            log(f"⑤ 清理: 删除知识库 {kb_id}...")
            for attempt in range(1, 4):
                try:
                    delete_knowledge_base(kb_id)
                    log("   知识库已删除")
                    break
                except KBError as e:
                    log(f"   删除失败（第 {attempt} 次）: {e}")
                    time.sleep(2 * attempt)
            else:
                cleanup_ok = False

    print("=" * 64)
    if ok:
        log(f"✅ 成功: faq.txt 已上传，且检索验证通过。证据: {evidence}")
    else:
        detail = "；".join(x for x in (status_note, fail_reason) if x)
        log(f"❌ 失败: 知识库文档不可用/不可检索。原因: {detail or '未知'}")
        log("   （知识库已清理，不会残留半成品）")
    if not cleanup_ok:
        log(f"⚠️ 知识库 {kb_id} 删除失败，请到智谱开放平台控制台手动删除，避免残留占用")
    return 0 if ok and cleanup_ok else (2 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
