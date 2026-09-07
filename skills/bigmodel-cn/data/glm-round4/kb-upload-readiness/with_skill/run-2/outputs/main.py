#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把脚本同目录的 faq.txt 灌进智谱开放平台（bigmodel.cn）托管知识库，并在宣布成功前做真实的可检索校验。

流程：
  1. 从环境变量 ZHIPUAI_API_KEY 读鉴权信息；
  2. 创建知识库（Embedding-3）；
  3. 上传 faq.txt（knowledge_type=1，按标题段落切，txt 的通用安全选择）；
  4. 轮询文档详情的 embedding_stat，直到向量化成功（=1）；
  5. 用 faq.txt 自身的真实内容当 query 调检索接口，确认能召回内容——检索为空就明确报错；
  6. 无论成功失败，最后删除知识库，不留垃圾。

两个必须知道的坑（官方文档 docs.bigmodel.cn + 真机验证得出）：
  * 这一族接口（/llm-application/open/*）出错时 HTTP 状态码依然是 200，真实结果在响应体
    的 code/message 里。所以本脚本一律判断 body["code"] == 200，不用 raise_for_status()。
  * 上传成功 != 可检索：向量化是后台异步任务，失败也没有主动通知（上传响应看起来完全正常）。
    唯一能看出真相的是 GET /llm-application/open/document/{id} 的 embedding_stat
    （0=处理中 1=成功 2=失败）；拿到 2 要读 failInfo.embedding_msg 把失败原因报给用户。
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"

EMBEDDING_ID = 11      # Embedding-3
KNOWLEDGE_TYPE = 1     # 按标题段落切（txt/doc/pdf/md 等通用）

REQUEST_TIMEOUT = (10, 60)   # (连接超时, 读取超时)，秒
MAX_API_RETRIES = 3          # 网络/限流/5xx 类错误的退避重试次数
RETRY_BACKOFF = 1.5          # 重试退避基数（秒），按指数递增

EMBED_POLL_INTERVAL = 5      # 轮询向量化状态的间隔（秒）
EMBED_POLL_TIMEOUT = 600     # 等向量化完成的最长时间（秒）

RETRIEVE_ATTEMPTS = 3        # 每个探测 query 的检索尝试次数（应对索引短暂延迟）
RETRIEVE_BACKOFF = 2.0       # 检索重试退避基数（秒）

# 限流/平台过载/用量上限类业务码，值得退避重试；鉴权、参数类错误重试无意义，直接失败
RETRYABLE_BIZ_CODES = {"1302", "1305", "1308", "1310"}

_HEADERS = {}


class KBError(Exception):
    """业务失败，message 直接面向用户说明原因。"""


def _error_of(body):
    """从响应体里抠出 (code, message)，兼容 llm-application 风格与 error 对象风格两种错误体。"""
    if isinstance(body, dict):
        if "code" in body:
            return body.get("code"), body.get("message", "")
        err = body.get("error")
        if isinstance(err, dict):
            return err.get("code"), err.get("message", "")
    return "", json.dumps(body, ensure_ascii=False)[:200]


def api_request(method, path, *, params=None, json_body=None, data=None, files=None):
    """发请求并校验业务码。

    这族接口出错时 HTTP 仍是 200，必须看响应体 code：code == 200 才算成功。
    仅对网络异常 / HTTP 429/5xx / 限流类业务码做退避重试。
    """
    url = BASE_URL + path
    last_err = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            resp = requests.request(method, url, params=params, json=json_body,
                                    data=data, files=files, headers=_HEADERS,
                                    timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络异常：{exc}"
        else:
            try:
                body = resp.json()
            except ValueError:
                raise KBError(f"{method} {path} 返回非 JSON 响应（HTTP {resp.status_code}）："
                              f"{(resp.text or '')[:200]}")
            status = resp.status_code
            if status == 429 or status >= 500:
                last_err = f"HTTP {status}：{(resp.text or '')[:200]}"
            else:
                code, message = _error_of(body)
                if str(code) == "200":
                    return body
                if str(code) in RETRYABLE_BIZ_CODES:
                    last_err = f"业务码 {code}：{message}"
                else:
                    raise KBError(f"{method} {path} 失败：code={code} message={message}")
        if attempt < MAX_API_RETRIES:
            time.sleep(RETRY_BACKOFF ** attempt)
    raise KBError(f"{method} {path} 重试 {MAX_API_RETRIES} 次仍失败，最后错误：{last_err}")


def find_faq_path():
    """定位 faq.txt：优先脚本同目录，其次当前工作目录。"""
    here = Path(__file__).resolve().parent
    for candidate in (here / "faq.txt", Path.cwd() / "faq.txt"):
        if candidate.is_file():
            return candidate
    raise KBError(f"找不到 faq.txt（先找了脚本同目录 {here}，再找了当前目录 {Path.cwd()}）")


def read_faq_text(path):
    """读 faq.txt 文本（仅用于挑检索探测 query；上传用的是原始字节）。"""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# 行首的编号/项目符号/问答前缀（1. / 12） / Q1： / 问： / - / # / [Q1] ……），只匹配行首
_BULLET_RE = re.compile(
    r"^(?:[\s#>\-*•·—\[\]]+|\d+\s*[.、）)\].:]?\s*|[QqAa]\d*[\]\）)\s]*[:：.、]|[问答]\s*[:：])+"
)


def _clean_line(line):
    out = line.strip()
    prev = None
    while prev != out:
        prev = out
        out = _BULLET_RE.sub("", out)
    return out.strip()


def pick_probe_queries(text, limit=3):
    """从 faq.txt 内容里挑真实文本行当检索探测 query。

    必须用文档自己的内容做 query：这样"检索为空"才能明确判定是"文档不可检索"，
    而不是"问了文档里没有的东西"。优先挑问句行（FAQ 场景下检索命中率最高）。
    """
    questions, others = [], []
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if len(line) < 6:
            continue
        (questions if ("？" in line or "?" in line) else others).append(line)
    seen, probes = set(), []
    for line in questions + others:
        probe = line[:60]
        if probe not in seen:
            seen.add(probe)
            probes.append(probe)
        if len(probes) >= limit:
            break
    return probes


def create_kb(name):
    body = api_request("POST", "/llm-application/open/knowledge", json_body={
        "embedding_id": EMBEDDING_ID,
        "name": name,
        "description": "faq.txt 上传+检索校验临时知识库，脚本结束后会删除",
    })
    kb_id = (body.get("data") or {}).get("id")
    if not kb_id:
        raise KBError(f"创建知识库的响应里没有 data.id：{json.dumps(body, ensure_ascii=False)[:300]}")
    return kb_id


def upload_document(kb_id, faq_path):
    # 读成 bytes 再传，这样 api_request 内部重试时可以原样重发（文件句柄会被耗尽，bytes 不会）
    files = {"files": (faq_path.name, faq_path.read_bytes(), "text/plain")}
    body = api_request(
        "POST",
        f"/llm-application/open/document/upload_document/{kb_id}",
        data={"knowledge_type": str(KNOWLEDGE_TYPE)},
        files=files,
    )
    data = body.get("data") or {}
    failed = data.get("failedInfos") or []
    if failed:
        reasons = "；".join(f"{f.get('fileName')}：{f.get('failReason')}" for f in failed)
        raise KBError(f"上传失败（failedInfos 非空）：{reasons}")
    infos = data.get("successInfos") or []
    if not infos or not infos[0].get("documentId"):
        raise KBError(f"上传响应异常，拿不到 documentId：{json.dumps(body, ensure_ascii=False)[:300]}")
    return infos[0]["documentId"]


def wait_embedding(doc_id):
    """轮询文档详情，直到向量化成功。embedding_stat：0=处理中 1=成功 2=失败。"""
    deadline = time.time() + EMBED_POLL_TIMEOUT
    last = {}
    while time.time() < deadline:
        body = api_request("GET", f"/llm-application/open/document/{doc_id}")
        info = body.get("data") or {}
        last = info
        stat = info.get("embedding_stat")
        if stat == 1:
            print(f"    向量化完成：word_num={info.get('word_num')} length={info.get('length')}")
            return info
        if stat == 2:
            fail = info.get("failInfo") or {}
            raise KBError(
                "文档向量化失败（embedding_stat=2），文档不可检索。"
                f"失败原因 failInfo：embedding_code={fail.get('embedding_code')}，"
                f"embedding_msg={fail.get('embedding_msg') or '（服务端未给出）'}"
            )
        print(f"    向量化处理中（embedding_stat={stat}），{EMBED_POLL_INTERVAL}s 后再查……")
        time.sleep(EMBED_POLL_INTERVAL)
    raise KBError(
        f"等待向量化超时（{EMBED_POLL_TIMEOUT}s）。最后状态：embedding_stat="
        f"{last.get('embedding_stat')}，failInfo={last.get('failInfo')}"
    )


def verify_retrieval(kb_id, doc_id, probes):
    """真实调一次检索接口，确认文档确实可被检索到——这是判定成功的硬性条件。"""
    for probe in probes:
        for attempt in range(1, RETRIEVE_ATTEMPTS + 1):
            body = api_request("POST", "/llm-application/open/knowledge/retrieve", json_body={
                "query": probe,
                "knowledge_ids": [kb_id],
                "top_k": 5,
            })
            hits = [h for h in (body.get("data") or []) if (h.get("text") or "").strip()]
            if hits:
                top = hits[0]
                meta = top.get("metadata") or {}
                meta_doc = meta.get("doc_id")
                if meta_doc and str(meta_doc) != str(doc_id):
                    print(f"    [提示] 命中文档 doc_id={meta_doc} 与本次上传的 {doc_id} 不一致"
                          f"（知识库是新建的，理论上不应发生，仅提示）")
                snippet = re.sub(r"\s+", " ", top.get("text", ""))[:80]
                print(f"    query：{probe}")
                print(f"    命中 {len(hits)} 条，Top1 score={top.get('score')}，"
                      f"doc_name={meta.get('doc_name')}")
                print(f"    Top1 片段：{snippet}……")
                return hits
            if attempt < RETRIEVE_ATTEMPTS:
                time.sleep(RETRIEVE_BACKOFF * attempt)
    total = len(probes) * RETRIEVE_ATTEMPTS
    raise KBError(
        f"检索校验失败：embedding_stat 已是 1（向量化显示成功），但用 faq.txt 自身内容作为 query "
        f"连续检索 {total} 次始终返回空（HTTP 200 + code 200 + data=[]）。"
        "这正是『上传显示成功、检索永远为空』的情况——文档虽标记为已向量化，索引实际不可用。"
        "建议到 bigmodel.cn 控制台查看该文档状态，或向平台反馈。按约定不判定为成功。"
    )


def cleanup_kb(kb_id):
    try:
        body = api_request("DELETE", f"/llm-application/open/knowledge/{kb_id}")
        print(f"    知识库已删除：{kb_id}（code={body.get('code')}）")
    except KBError as exc:
        print(f"    [警告] 删除知识库 {kb_id} 失败：{exc}")
        print(f"    [警告] 请到 bigmodel.cn 控制台手动删除知识库 {kb_id}，避免占用配额。")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("[失败] 环境变量 ZHIPUAI_API_KEY 未设置。请先 export ZHIPUAI_API_KEY=你的Key 再运行。")
        return 1
    _HEADERS["Authorization"] = f"Bearer {api_key}"

    # 建库之前先把本地输入准备好，缺文件直接失败，不在服务端留任何东西
    try:
        faq_path = find_faq_path()
        raw_len = faq_path.stat().st_size
        if raw_len == 0:
            raise KBError(f"{faq_path} 是空文件，没有可上传的内容。")
        text = read_faq_text(faq_path)
        probes = pick_probe_queries(text)
        if not probes:
            raise KBError("faq.txt 里找不到长度足够的文本行，无法构造检索校验用的 query。")
    except KBError as exc:
        print(f"[失败] {exc}")
        return 1

    kb_name = f"faq-upload-check-{time.strftime('%Y%m%d%H%M%S')}"
    kb_id = None
    try:
        print(f"[1/5] 创建知识库（embedding_id={EMBEDDING_ID}，name={kb_name}）……")
        kb_id = create_kb(kb_name)
        print(f"    知识库 ID：{kb_id}")

        print(f"[2/5] 上传文档 {faq_path}（{raw_len} 字节，knowledge_type={KNOWLEDGE_TYPE}）……")
        doc_id = upload_document(kb_id, faq_path)
        print(f"    文档 ID：{doc_id}")

        print(f"[3/5] 轮询向量化状态（间隔 {EMBED_POLL_INTERVAL}s，最长等 {EMBED_POLL_TIMEOUT}s）……")
        wait_embedding(doc_id)

        print("[4/5] 检索校验：用 faq.txt 里的真实内容当 query 实测检索……")
        verify_retrieval(kb_id, doc_id, probes)

        print()
        print("✅ 成功：faq.txt 已灌入知识库，且已通过真实检索验证（文档确实可以被检索到）。")
        return 0
    except KBError as exc:
        print()
        print(f"❌ 失败：{exc}")
        return 1
    except KeyboardInterrupt:
        print()
        print("❌ 中断：用户手动中断。")
        return 130
    finally:
        print()
        print("[5/5] 清理：删除本次创建的知识库（无论成败）……")
        if kb_id:
            cleanup_kb(kb_id)
        else:
            print("    知识库未创建成功，无需清理。")


if __name__ == "__main__":
    sys.exit(main())
