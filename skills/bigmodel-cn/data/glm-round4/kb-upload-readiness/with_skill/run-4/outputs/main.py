#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱（bigmodel.cn）托管知识库，并确认真的可检索。

流程：建库 -> 上传文档 -> 校验可检索 -> 无论成败都删除知识库。

为什么"上传成功"之后还必须校验（本脚本的核心）：
  1. /llm-application/open/* 这一族接口业务出错时 HTTP 状态码依然是 200，
     真实结果在响应体的 code 字段里，所以不能只看 raise_for_status()，
     必须判断 body["code"] == 200。
  2. 上传返回 successInfos/documentId 只代表"受理成功"，向量化是后台异步任务，
     失败时没有任何主动通知。必须轮询 GET /llm-application/open/document/{id}
     直到 embedding_stat == 1（0=处理中，1=成功，2=失败）；变成 2 就把
     failInfo.embedding_code / embedding_msg 的失败原因报出来。
  3. 向量化成功后还要真的检索一次：query 取自 faq.txt 自身内容（文档里必然
     存在的问题），召回为空就按失败处理——这正是"上传显示成功、检索永远为空"
     的坑，不能报喜不报忧。

用法：
    ZHIPUAI_API_KEY=你的key python3 main.py
"""

import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
API_KEY_ENV = "ZHIPUAI_API_KEY"
HTTP_TIMEOUT = 60         # 单次 HTTP 请求超时（秒）
POLL_INTERVAL = 5         # 轮询向量化状态的间隔（秒）
EMBEDDING_TIMEOUT = 600   # 等向量化完成的最长时间（秒）
RETRIEVE_RETRY_DELAY = 10 # 检索为空时重试的间隔（秒）


class KBError(RuntimeError):
    """流程中任何一步失败，message 必须带原因。"""


def api(method, path, api_key, **kwargs):
    """统一请求封装：这一族接口业务失败时 HTTP 仍是 200，必须看响应体的 code。"""
    url = BASE_URL + path
    try:
        resp = requests.request(
            method, url,
            headers={"Authorization": "Bearer " + api_key},
            timeout=HTTP_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise KBError(f"{method} {url} 网络请求异常：{exc}") from exc

    try:
        body = resp.json()
    except ValueError:
        raise KBError(
            f"{method} {url} 返回非 JSON 响应（HTTP {resp.status_code}）：{resp.text[:300]}"
        ) from None

    if resp.status_code != 200 or body.get("code") != 200:
        raise KBError(
            f"{method} {url} 失败：HTTP {resp.status_code}，"
            f"code={body.get('code')}，message={body.get('message')}"
        )
    return body


def pick_probe_query(faq_text):
    """从 faq.txt 自身内容里挑一个探测查询。

    必须用文档里真实存在的问题去检索：查不到才能断定是知识库不可用，
    而不是拿一个文档里本来就没有的问题误报失败。
    """
    for line in faq_text.splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        if "？" in line or "?" in line or line.upper().startswith(("Q", "问")):
            return line[:200]  # 接口限制 query 不超过 1000 字，截断留足余量
    # 兜底：没有明显的问答格式，就用第一行非空文本
    return next((l.strip() for l in faq_text.splitlines() if l.strip()), "")[:200]


def wait_until_indexed(api_key, document_id):
    """轮询文档详情直到向量化成功；失败或超时都明确报错。

    embedding_stat 官方 schema 未枚举取值，按实测语义处理：
    0=处理中，1=成功，2=失败（失败原因在 failInfo 里）。
    """
    deadline = time.monotonic() + EMBEDDING_TIMEOUT
    last_stat, last_fail = None, {}
    consecutive_errors = 0
    while time.monotonic() < deadline:
        try:
            body = api("GET", f"/llm-application/open/document/{document_id}", api_key)
            consecutive_errors = 0
        except KBError as exc:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                raise KBError(f"连续 {consecutive_errors} 次查询文档状态失败，中止等待：{exc}")
            time.sleep(POLL_INTERVAL)
            continue

        doc = body.get("data") or {}
        last_stat = doc.get("embedding_stat")
        last_fail = doc.get("failInfo") or {}
        if last_stat == 1:
            print(f"    向量化完成（word_num={doc.get('word_num')}）")
            return
        if last_stat == 2:
            raise KBError(
                "文档向量化失败：上传接口虽然返回了成功，但后台向量化没有做成。"
                f"失败原因：failInfo.embedding_code={last_fail.get('embedding_code')}，"
                f"embedding_msg={last_fail.get('embedding_msg') or '（接口未返回具体原因）'}"
            )
        print(f"    向量化处理中（embedding_stat={last_stat}），{POLL_INTERVAL}s 后再查…")
        time.sleep(POLL_INTERVAL)

    raise KBError(
        f"等待向量化超时（{EMBEDDING_TIMEOUT}s），最后状态 embedding_stat={last_stat}，"
        "文档未能确认可检索，按失败处理。"
    )


def verify_retrievable(api_key, knowledge_id, document_id, query):
    """真实检索一次：召回为空就是不可用，不能只看向量化状态。"""
    print(f"    探测查询：{query}")
    methods = ["mixed", "mixed", "keyword"]  # 索引生效可能略有延迟，空了先重试再退到关键词
    for i, method in enumerate(methods, 1):
        body = api(
            "POST", "/llm-application/open/knowledge/retrieve", api_key,
            json={
                "query": query,
                "knowledge_ids": [knowledge_id],
                "document_ids": [document_id],
                "top_k": 5,
                "recall_method": method,
            },
        )
        hits = body.get("data") or []
        if hits:
            best = hits[0]
            snippet = str(best.get("text") or "").replace("\n", " ")[:80]
            print(f"    检索命中 {len(hits)} 条（recall_method={method}），"
                  f"最高分 {best.get('score')}，片段：{snippet}…")
            return
        print(f"    第 {i} 次检索（recall_method={method}）结果为空…")
        if i < len(methods):
            time.sleep(RETRIEVE_RETRY_DELAY)

    raise KBError(
        "检索校验未通过：文档向量化状态显示成功，但对来自 faq.txt 自身内容的查询 "
        f"『{query}』连续 {len(methods)} 次检索均为空——知识库实际不可用，"
        "这就是『上传显示成功、检索永远为空』的情况，不能当作成功。"
    )


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"[失败] 请先设置环境变量 {API_KEY_ENV}", file=sys.stderr)
        return 1

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    if not faq_path.is_file():
        print(f"[失败] 找不到 {faq_path}", file=sys.stderr)
        return 1
    faq_text = faq_path.read_text(encoding="utf-8")
    if not faq_text.strip():
        print(f"[失败] {faq_path} 是空文件", file=sys.stderr)
        return 1
    print(f"已读取 {faq_path.name}（{len(faq_text.splitlines())} 行）")

    knowledge_id = None
    try:
        print("步骤 1/4：创建知识库…")
        body = api("POST", "/llm-application/open/knowledge", api_key, json={
            "embedding_id": 11,  # Embedding-3
            "name": "faq-upload-check-" + time.strftime("%Y%m%d%H%M%S"),
            "description": "main.py 上传+可检索校验用的临时知识库，脚本结束会删除",
        })
        knowledge_id = (body.get("data") or {}).get("id")
        if not knowledge_id:
            raise KBError(f"创建知识库的响应里没有 data.id：{body}")
        print(f"    知识库已创建：{knowledge_id}")

        print("步骤 2/4：上传 faq.txt…")
        with faq_path.open("rb") as fh:
            body = api(
                "POST",
                f"/llm-application/open/document/upload_document/{knowledge_id}",
                api_key,
                files={"files": (faq_path.name, fh, "text/plain")},
                # knowledge_type 不传，交给平台按文档格式动态解析
            )
        infos = body.get("data") or {}
        failed = infos.get("failedInfos") or []
        if failed:
            reasons = "；".join(
                f"{f.get('fileName')}: {f.get('failReason')}" for f in failed)
            raise KBError(f"上传接口报告有文件失败：{reasons}")
        success = infos.get("successInfos") or []
        document_id = (success[0] or {}).get("documentId") if success else None
        if not document_id:
            raise KBError(f"上传响应里没有拿到 documentId：{body}")
        print(f"    上传受理成功：documentId={document_id}"
              "（只是受理，向量化仍在后台进行，继续校验）")

        print("步骤 3/4：校验文档真正可用（向量化状态 + 真实检索）…")
        wait_until_indexed(api_key, document_id)
        verify_retrievable(api_key, knowledge_id, document_id, pick_probe_query(faq_text))

        print("步骤 4/4：校验通过。")
        print()
        print("[成功] faq.txt 已灌入知识库，且已真实检索命中，确认可用：")
        print(f"       知识库ID：{knowledge_id}")
        print(f"       文档ID：{document_id}")
        print("       （按任务要求，下方清理环节会删除这个知识库）")
        return 0
    except KBError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    finally:
        if knowledge_id:
            print()
            print("清理：删除本次创建的知识库…")
            try:
                api("DELETE", f"/llm-application/open/knowledge/{knowledge_id}", api_key)
                print(f"    已删除知识库 {knowledge_id}")
            except KBError as exc:
                print(f"[警告] 知识库 {knowledge_id} 删除失败，请到控制台手动清理！原因：{exc}",
                      file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
