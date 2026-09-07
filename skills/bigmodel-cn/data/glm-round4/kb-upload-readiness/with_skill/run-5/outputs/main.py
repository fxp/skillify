#!/usr/bin/env python3
"""把同目录下的 faq.txt 灌进智谱开放平台托管知识库，并在宣告成功前校验文档确实可检索。

流程：创建知识库 → 上传 faq.txt → 轮询向量化状态 → 真实检索验证 → 无论成败都删除知识库。

两个必须先知道的接口行为（来自对真实 API 的实测）：
1. 这族接口（/llm-application/open/*）出错时 HTTP 状态码依然是 200，真实结果在响应体
   的 code 字段里，所以 raise_for_status() 在这里永远不触发，必须检查 code == 200。
2. 上传成功 ≠ 文档可检索：向量化是后台异步任务，失败时没有任何主动通知，检索接口
   也只会一直返回空数组而不报错。唯一可靠的判据是 GET /document/{id} 的
   embedding_stat（0=处理中 1=成功 2=失败，失败原因在 failInfo.embedding_msg），
   再加上真实调一次检索接口确认能召回切片。两层都通过本脚本才宣告成功。

用法：
    export ZHIPUAI_API_KEY=...
    python3 main.py
"""

import os
import sys
import time
import uuid
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
FAQ_PATH = Path(__file__).resolve().parent / "faq.txt"

EMBEDDING_ID = 11        # 向量化模型：Embedding-3
KNOWLEDGE_TYPE = 1       # 切片方式：按标题段落切（支持 txt）
HTTP_TIMEOUT = 60        # 单次 HTTP 请求超时（秒）
EMBEDDING_TIMEOUT = 300  # 等向量化完成的最长时间（秒）
RETRIEVE_TIMEOUT = 60    # 等检索可用的最长时间（秒）
POLL_INTERVAL = 5        # 轮询间隔（秒）

API_KEY = os.environ.get("ZHIPUAI_API_KEY", "")


class KBError(RuntimeError):
    """流程中任何一步失败；message 必须写清原因，不许含糊。"""


def api(method, path, *, params=None, json_body=None, data=None, files=None):
    """发请求并校验业务码。

    这族接口出错时 HTTP 仍是 200，真实结果在 body.code，所以这里统一判 code == 200；
    对网络错误 / HTTP 429 / 5xx 做指数退避重试，其余（鉴权、参数类）重试无意义，直接失败。
    """
    url = BASE_URL + path
    headers = {"Authorization": f"Bearer {API_KEY}"}
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.request(method, url, headers=headers, params=params,
                                    json=json_body, data=data, files=files,
                                    timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络错误：{exc!r}"
        else:
            if resp.status_code < 500 and resp.status_code != 429:
                try:
                    body = resp.json()
                except ValueError:
                    raise KBError(f"{method} {path} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:300]}")
                # 业务码不为 200 时，body 里就是 LlmApplicationError 的 code/message
                if resp.status_code != 200 or body.get("code") != 200:
                    raise KBError(f"{method} {path} 失败：HTTP {resp.status_code}，业务响应：{str(body)[:300]}")
                return body
            last_err = f"HTTP {resp.status_code}：{resp.text[:200]}"
        if attempt < 3:
            time.sleep(2 ** (attempt - 1))
    raise KBError(f"{method} {path} 重试 3 次仍失败，最后错误：{last_err}")


def upload_document(knowledge_id):
    """上传 faq.txt，返回 documentId。上传被拒/拿不到 documentId 都立刻报错。"""
    with FAQ_PATH.open("rb") as fh:
        body = api("POST", f"/llm-application/open/document/upload_document/{knowledge_id}",
                   data={"knowledge_type": str(KNOWLEDGE_TYPE)},
                   files={"files": (FAQ_PATH.name, fh, "text/plain")})
    payload = body.get("data") or {}
    failed = payload.get("failedInfos") or []
    if failed:
        reasons = "；".join(f"{i.get('fileName')}：{i.get('failReason')}" for i in failed)
        raise KBError(f"上传被服务端拒绝：{reasons}")
    doc_id = next((i.get("documentId") for i in payload.get("successInfos") or []
                   if i.get("documentId")), None)
    if not doc_id:
        raise KBError(f"上传响应里没有 documentId（successInfos 为空），无法进入校验环节：{str(body)[:300]}")
    return doc_id


def wait_embedding_ready(document_id):
    """轮询文档详情直到向量化成功（embedding_stat==1）。

    embedding_stat: 0=处理中 1=成功 2=失败。失败时把 failInfo 里的原因原样报给用户；
    未知取值按未完成处理（打印警告），超时则明确报错，绝不把“还在处理中”当成功。
    """
    deadline = time.time() + EMBEDDING_TIMEOUT
    last_stat = None
    while time.time() < deadline:
        doc = (api("GET", f"/llm-application/open/document/{document_id}").get("data")) or {}
        stat = doc.get("embedding_stat")
        if stat != last_stat:
            print(f"    文档 {document_id} 向量化状态：embedding_stat={stat}"
                  f"（0=处理中 1=成功 2=失败）")
            last_stat = stat
        if stat == 1:
            print(f"    向量化完成（word_num={doc.get('word_num')}）")
            return
        if stat == 2:
            fail = doc.get("failInfo") or {}
            raise KBError(f"文档向量化失败：embedding_code={fail.get('embedding_code')}，"
                          f"embedding_msg={fail.get('embedding_msg') or '（服务端未给出原因）'}。"
                          f"上传接口当时显示成功，但后台向量化已失败，此文档不可检索。")
        if stat != 0:
            print(f"    注意：embedding_stat={stat} 不是已知取值，按未完成继续等待……")
        time.sleep(POLL_INTERVAL)
    raise KBError(f"等待 {EMBEDDING_TIMEOUT}s 后向量化仍未完成"
                  f"（最后观察到的 embedding_stat={last_stat}），无法确认可检索，按失败处理。")


def pick_probe_query(content):
    """从 faq.txt 自身内容里挑一段有区分度的文本做检索探针，保证“查得到”是有意义的判据。"""
    for line in content.splitlines():
        s = line.strip()
        if len(s) >= 8:
            return s[:60]
    return content.strip()[:60] or "常见问题"


def verify_retrievable(knowledge_id, document_id, content):
    """用文档原文片段真实调检索接口，确认能召回属于本文档的切片，否则报错。"""
    query = pick_probe_query(content)
    print(f"    用探针 query 检索：{query}")
    deadline = time.time() + RETRIEVE_TIMEOUT
    last_note = ""
    while time.time() < deadline:
        for method in ("mixed", "keyword"):  # mixed 为空再退到 keyword，避免索引刚就绪时的偶发空结果
            body = api("POST", "/llm-application/open/knowledge/retrieve",
                       json_body={"query": query,
                                  "knowledge_ids": [knowledge_id],
                                  "document_ids": [document_id],
                                  "top_k": 5,
                                  "recall_method": method})
            hits = body.get("data") or []
            if hits:
                # 召回的切片必须确实来自刚上传的文档，否则不算通过
                doc_ids = {((h.get("metadata") or {}).get("doc_id")) for h in hits}
                known = {d for d in doc_ids if d}
                if known and document_id not in known:
                    raise KBError(f"检索有结果但不属于刚上传的文档（期望 doc_id={document_id}，"
                                  f"实际={sorted(known)}），不能视为校验通过。")
                top = hits[0]
                meta = top.get("metadata") or {}
                print(f"    命中 {len(hits)} 条切片（{method} 检索），top1 score={top.get('score')}，"
                      f"来源={meta.get('doc_name') or meta.get('doc_id')}")
                print(f"    top1 片段：{str(top.get('text'))[:80]}……")
                return
            last_note = f"{method} 检索返回空列表（code=200，无报错）"
        time.sleep(POLL_INTERVAL)
    raise KBError(f"校验失败：向量化状态已是成功，但用文档原文片段“{query}”在 "
                  f"{RETRIEVE_TIMEOUT}s 内始终检索不到任何切片（{last_note}）。"
                  f"这就是“上传显示成功、检索永远为空”的状态，请按失败处理并排查账号/服务端。")


def cleanup(knowledge_id):
    """无论成败都删除本次创建的知识库；删不掉也要让用户知道去哪手动清理。"""
    if not knowledge_id:
        return
    try:
        api("DELETE", f"/llm-application/open/knowledge/{knowledge_id}")
        print(f"[清理] 知识库 {knowledge_id} 已删除")
    except KBError as exc:
        print(f"[清理] 警告：知识库 {knowledge_id} 删除失败，请到控制台手动删除：{exc}",
              file=sys.stderr)


def main():
    if not API_KEY:
        print("错误：环境变量 ZHIPUAI_API_KEY 未设置（需为标准 API Key，不是 Coding Plan 套餐 Key）。",
              file=sys.stderr)
        return 1
    if not FAQ_PATH.is_file():
        print(f"错误：找不到 {FAQ_PATH}", file=sys.stderr)
        return 1
    content = FAQ_PATH.read_text(encoding="utf-8")
    if not content.strip():
        print(f"错误：{FAQ_PATH} 是空文件，没有可导入的内容。", file=sys.stderr)
        return 1

    knowledge_id = None
    try:
        print("[1/4] 创建知识库（Embedding-3）……")
        body = api("POST", "/llm-application/open/knowledge",
                   json_body={"embedding_id": EMBEDDING_ID,
                              "name": f"faq-upload-verify-{uuid.uuid4().hex[:8]}",
                              "description": "main.py 临时创建：上传 faq.txt 并校验可检索，脚本结束自动删除",
                              "background": "blue", "icon": "book"})
        knowledge_id = (body.get("data") or {}).get("id")
        if not knowledge_id:
            raise KBError(f"创建知识库响应里没有 data.id：{str(body)[:300]}")
        print(f"    知识库 ID：{knowledge_id}")

        print(f"[2/4] 上传 {FAQ_PATH.name}（{len(content.splitlines())} 行）……")
        document_id = upload_document(knowledge_id)
        print(f"    上传受理成功，documentId={document_id}")

        print("[3/4] 等待后台向量化完成（上传成功≠可检索，必须等状态确认）……")
        wait_embedding_ready(document_id)

        print("[4/4] 检索校验：确认文档确实可以被检索到……")
        verify_retrievable(knowledge_id, document_id, content)

        print("\n成功：faq.txt 已导入知识库，且已通过真实检索验证（向量化成功 + 检索召回切片）。")
        print("知识库已按约定清理，本次流程结束。")
        return 0
    except KBError as exc:
        print(f"\n失败：{exc}", file=sys.stderr)
        return 1
    finally:
        cleanup(knowledge_id)


if __name__ == "__main__":
    sys.exit(main())
