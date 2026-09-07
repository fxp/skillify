#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱托管知识库，并在宣布成功前完成可检索性校验。

流程：建库 -> 上传文档 -> 轮询向量化状态 -> 真实检索校验 -> 清理知识库。

两个必须知道的接口行为（来自官方文档与真实调用验证）：
1. 这族 /llm-application/open/* 接口出错时 HTTP 状态码依然是 200，
   真实成败在响应体的 code 字段里（200 才是成功），不能只看 HTTP 状态码。
2. 上传接口返回成功只代表文件被接收，向量化是后台异步进行的，失败不会有任何
   主动通知；期间检索只会返回空数组（code 200, data: []），无限等也等不来结果。
   唯一能看出真相的是文档详情接口的 embedding_stat：
   0=处理中  1=成功  2=失败（失败原因在 failInfo.embedding_code / embedding_msg）。

因此本脚本在打印"成功"之前会依次确认：
  a. 每个文档 embedding_stat == 1（向量化真正完成）；
  b. 用 faq.txt 原文内容作为查询词，对知识库发起真实检索且结果非空。
任何一步不满足都会带着具体原因报错退出（退出码非 0），不报喜不报忧。
无论成败，最后都会删除本次创建的知识库。

依赖：仅 requests。用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
EMBEDDING_ID = 11  # Embedding-3
KB_NAME_PREFIX = "faq-upload-verify"
POLL_TIMEOUT = 300   # 等待向量化完成的最长秒数
POLL_INTERVAL = 5    # 轮询文档详情的间隔秒数
RETRIEVE_ATTEMPTS = 3  # 检索为空时的重试次数（防御索引刚建好的短暂延迟）


class FlowError(RuntimeError):
    """流程中任何一步失败，message 里带具体原因。"""


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api(method: str, path: str, *, params=None, json_body=None, files=None, data=None):
    """发请求并校验业务码。这族接口失败时 HTTP 仍是 200，必须看 body 里的 code。"""
    try:
        resp = requests.request(
            method,
            BASE_URL + path,
            headers={"Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"},
            params=params,
            json=json_body,
            files=files,
            data=data,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise FlowError(f"{method} {path} 网络请求异常：{exc}") from exc

    if resp.status_code != 200:
        # 正常情况下业务错误也返回 HTTP 200；走到这里说明问题更底层，原样带出。
        raise FlowError(
            f"{method} {path} 返回了非 200 的 HTTP 状态码 {resp.status_code}：{resp.text[:300]}"
        )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise FlowError(
            f"{method} {path} 返回的内容不是 JSON（HTTP {resp.status_code}）：{resp.text[:300]}"
        ) from exc
    if payload.get("code") != 200:
        raise FlowError(
            f"{method} {path} 业务失败：code={payload.get('code')}，"
            f"message={payload.get('message')!r}（注意：这类接口失败时 HTTP 状态码仍是 200）"
        )
    return payload


def pick_query(faq_text: str) -> str:
    """从 faq.txt 原文里取第一条非空行作为检索查询词。

    用文档自己的内容做查询，相关性是最高的；这样"检索为空"就只能是服务端
    索引没生效，而不是"问题确实和文档无关"，避免误判。
    """
    for line in faq_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:60]
    raise FlowError("无法从 faq.txt 中提取用于校验的查询词（文件没有非空行）")


def create_knowledge_base() -> str:
    payload = api(
        "POST",
        "/llm-application/open/knowledge",
        json_body={
            "embedding_id": EMBEDDING_ID,
            "name": f"{KB_NAME_PREFIX}-{time.strftime('%Y%m%d%H%M%S')}",
            "description": "临时知识库：faq.txt 上传与可检索性校验，脚本结束即删除",
        },
    )
    knowledge_id = (payload.get("data") or {}).get("id")
    if not knowledge_id:
        raise FlowError(f"创建知识库成功但响应里没有 data.id：{payload}")
    log(f"1/5 知识库创建成功：knowledge_id={knowledge_id}")
    return knowledge_id


def upload_faq(knowledge_id: str, faq_path: Path) -> str:
    with faq_path.open("rb") as fh:
        payload = api(
            "POST",
            f"/llm-application/open/document/upload_document/{knowledge_id}",
            files={"files": (faq_path.name, fh, "text/plain")},
            data={"knowledge_type": 1},  # 1 = 按标题段落切，支持 txt
        )
    doc_data = payload.get("data") or {}
    failed = doc_data.get("failedInfos") or []
    if failed:
        raise FlowError(f"上传接口报告有文件失败：{failed}")
    success_infos = doc_data.get("successInfos") or []
    if not success_infos:
        raise FlowError(f"上传接口既无 successInfos 也无 failedInfos，响应异常：{payload}")
    document_id = success_infos[0].get("documentId")
    if not document_id:
        raise FlowError(f"上传接口的 successInfos 里缺少 documentId：{success_infos}")
    log(f"2/5 faq.txt 上传被接受：document_id={document_id}"
        "（注意：这只代表文件被接收，向量化还在后台异步进行）")
    return document_id


def wait_embedding_done(document_id: str) -> None:
    """轮询文档详情，直到向量化真正完成（embedding_stat=1）。

    embedding_stat=2 说明向量化失败，此时检索会永远返回空数组且没有任何主动
    通知——必须在这里把 failInfo 里的失败原因直接报出来，而不是傻等检索结果。
    """
    deadline = time.monotonic() + POLL_TIMEOUT
    last_stat = None
    while time.monotonic() < deadline:
        doc = api("GET", f"/llm-application/open/document/{document_id}").get("data") or {}
        last_stat = doc.get("embedding_stat")
        if last_stat == 1:
            log(f"3/5 向量化完成：embedding_stat=1（word_num={doc.get('word_num')}）")
            return
        if last_stat == 2:
            fail_info = doc.get("failInfo") or {}
            raise FlowError(
                "向量化失败（embedding_stat=2），文档不可检索。"
                f"失败原因：embedding_code={fail_info.get('embedding_code')}，"
                f"embedding_msg={fail_info.get('embedding_msg')!r}"
            )
        log(f"      向量化进行中（embedding_stat={last_stat}），{POLL_INTERVAL}s 后再查…")
        time.sleep(POLL_INTERVAL)
    raise FlowError(
        f"等待向量化超时（{POLL_TIMEOUT}s）：embedding_stat 始终停在 {last_stat}，"
        "文档迟迟没有进入可检索状态"
    )


def verify_retrievable(knowledge_id: str, query: str) -> None:
    """用文档原文做查询词发起真实检索，结果非空才算校验通过。"""
    last_payload_data = []
    for attempt in range(1, RETRIEVE_ATTEMPTS + 1):
        payload = api(
            "POST",
            "/llm-application/open/knowledge/retrieve",
            json_body={"query": query, "knowledge_ids": [knowledge_id], "top_k": 5},
        )
        last_payload_data = payload.get("data") or []
        if last_payload_data:
            top = last_payload_data[0]
            text_preview = (top.get("text") or "").strip().replace("\n", " ")[:80]
            log(f"4/5 检索校验通过：命中 {len(last_payload_data)} 条切片，"
                f"最高分 score={top.get('score')}，内容开头：{text_preview!r}")
            return
        if attempt < RETRIEVE_ATTEMPTS:
            log(f"      检索返回空结果（第 {attempt}/{RETRIEVE_ATTEMPTS} 次），"
                f"{POLL_INTERVAL}s 后重试…")
            time.sleep(POLL_INTERVAL)
    raise FlowError(
        f"可检索性校验失败：向量化状态虽然是成功，但用文档原文 "
        f"（查询词 {query!r}）连续 {RETRIEVE_ATTEMPTS} 次真实检索都返回空结果"
        "（HTTP 200、code 200、data: []）。这正是『上传显示成功但检索永远为空』的"
        "症状：服务端索引实际没有生效。请到智谱控制台核对文档状态，或联系平台排查；"
        "本脚本不宣布成功。"
    )


def cleanup(knowledge_id: str) -> None:
    api("DELETE", f"/llm-application/open/knowledge/{knowledge_id}")
    log(f"5/5 知识库已清理（DELETE {knowledge_id}）")


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("[错误] 环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API。", file=sys.stderr)
        return 2

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    if not faq_path.is_file():
        print(f"[错误] 找不到 {faq_path}，请把 faq.txt 放在脚本同目录下。", file=sys.stderr)
        return 2
    try:
        faq_text = faq_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        print(f"[错误] faq.txt 不是 UTF-8 编码，无法读取：{exc}", file=sys.stderr)
        return 2
    if not faq_text.strip():
        print("[错误] faq.txt 是空文件，没有可上传的内容。", file=sys.stderr)
        return 2
    query = pick_query(faq_text)
    log(f"准备上传 {faq_path}（{len(faq_text.splitlines())} 行），校验用查询词：{query!r}")

    knowledge_id = None
    try:
        knowledge_id = create_knowledge_base()
        document_id = upload_faq(knowledge_id, faq_path)
        wait_embedding_done(document_id)
        verify_retrievable(knowledge_id, query)
        print(
            "\n成功：faq.txt 已灌入知识库并验证可被检索"
            f"（knowledge_id={knowledge_id}，document_id={document_id}）。"
            "知识库已按约定清理。"
        )
        return 0
    except FlowError as exc:
        print(f"\n失败：{exc}", file=sys.stderr)
        return 1
    finally:
        if knowledge_id:
            try:
                cleanup(knowledge_id)
            except FlowError as exc:
                print(
                    f"[警告] 知识库清理失败，请手动删除（knowledge_id={knowledge_id}，"
                    f"控制台 https://bigmodel.cn/usercenter/knowledge）：{exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    sys.exit(main())
