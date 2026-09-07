#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 faq.txt 灌进智谱（bigmodel.cn）托管知识库：建库 -> 上传 -> 验证可检索 -> 清理。

只有当"文档真的能被检索到"才报告成功，验证分两层：
  1) 轮询文档详情直到 embedding_stat == 1（0=处理中 1=成功 2=失败）；
  2) 再调用检索接口实测一次，必须命中本次上传文档的切片才算数。

为什么不能只看上传接口的返回（两个实测踩过的坑）：
  - 这族 llm-application/open/* 接口出错时 HTTP 状态码仍是 200，真实结果在响应体
    code 里（如 100013 知识库不存在），resp.raise_for_status() 拦不住；
  - 上传返回成功只代表文件收下了，切分/向量化是后台异步任务，失败没有任何主动通知，
    检索会一直返回 HTTP 200 + data=[]（空数组），无限等也不会有结果。所以必须看
    embedding_stat，且最终以一次真实检索为准。

无论成败，最后都会删除本次创建的知识库。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import os
import sys
import time
import traceback
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
EMBEDDING_ID = 11  # Embedding-3；可选 3=Embedding-2 / 11=Embedding-3 / 12=Embedding-3-pro
KNOWLEDGE_TYPE = 1  # 按标题段落切（faq.txt 为逐行问题，txt 适用该模式）

HTTP_TIMEOUT = 60         # 单次 HTTP 请求超时（秒）
EMBEDDING_TIMEOUT = 300   # 等向量化完成的总时限（秒）
POLL_INTERVAL = 5         # 轮询文档向量化状态的间隔（秒）
RETRIEVE_ATTEMPTS = 6     # 检索验证重试次数（索引刚建好可能短暂查不到）
RETRIEVE_INTERVAL = 5     # 检索重试间隔（秒）


class StepError(RuntimeError):
    """流程错误。transient=True 表示可能是一时性故障，轮询时可以继续等。"""

    def __init__(self, message, transient=False):
        super().__init__(message)
        self.transient = transient


def request_api(method, path, headers, **kwargs):
    """发请求并按这套接口的真实约定判定成败：必须看响应体 code，不能只看 HTTP 状态码。"""
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    try:
        resp = requests.request(method, BASE_URL + path, headers=headers, **kwargs)
    except requests.RequestException as exc:
        raise StepError(f"网络请求失败 {method} {path}：{exc}", transient=True) from exc
    try:
        body = resp.json()
    except ValueError:
        raise StepError(
            f"{method} {path} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]!r}",
            transient=resp.status_code >= 500,
        ) from None
    if resp.status_code != 200 or body.get("code") != 200:
        raise StepError(
            f"{method} {path} 失败：HTTP {resp.status_code}，"
            f"业务 code={body.get('code')}，message={body.get('message')}"
        )
    return body


def create_knowledge(headers):
    name = time.strftime("faq-kb-verify-%Y%m%d-%H%M%S")
    body = request_api(
        "POST", "/llm-application/open/knowledge", headers,
        json={
            "embedding_id": EMBEDDING_ID,
            "embedding_model": "Embedding-3",
            "name": name,
            "description": "main.py 上传+检索验证用临时知识库，脚本结束自动删除",
        },
    )
    try:
        return body["data"]["id"]
    except (KeyError, TypeError):
        raise StepError(f"创建知识库返回结构异常，未拿到知识库 id：{body}") from None


def upload_faq(headers, knowledge_id, faq_path):
    # 注意 headers 里只放 Authorization，Content-Type 由 requests 按 multipart 自动生成
    with faq_path.open("rb") as fh:
        body = request_api(
            "POST", f"/llm-application/open/document/upload_document/{knowledge_id}",
            headers,
            files={"files": (faq_path.name, fh, "text/plain")},
            data={"knowledge_type": KNOWLEDGE_TYPE},
        )
    infos = (body.get("data") or {}).get("successInfos") or []
    failed = (body.get("data") or {}).get("failedInfos") or []
    if failed:
        raise StepError(f"上传存在失败项：{failed}")
    doc_ids = [item.get("documentId") for item in infos]
    if not doc_ids or any(not d for d in doc_ids):
        raise StepError(f"上传返回 code=200 但缺少 documentId，响应：{body}")
    return doc_ids


def wait_embedding(headers, doc_ids):
    """轮询文档详情直到全部 embedding_stat==1；==2 或超时立即报错，不带病往下走。"""
    print(f"[3/5] 等待向量化完成（最多 {EMBEDDING_TIMEOUT} 秒，每 {POLL_INTERVAL} 秒查一次）...")
    deadline = time.time() + EMBEDDING_TIMEOUT
    pending = list(doc_ids)
    while pending:
        time.sleep(POLL_INTERVAL)
        if time.time() > deadline:
            raise StepError(
                f"等待向量化超时（{EMBEDDING_TIMEOUT} 秒），以下文档仍未完成：{pending}。"
                "无法确认文档可检索，按失败处理。"
            )
        for doc_id in list(pending):
            try:
                body = request_api("GET", f"/llm-application/open/document/{doc_id}", headers)
            except StepError as exc:
                if exc.transient:
                    print(f"      查询文档状态暂时失败，继续等待：{exc}")
                    continue
                raise
            data = body.get("data") or {}
            stat = data.get("embedding_stat")
            if stat == 1:
                print(f"      文档 {doc_id} 向量化成功（embedding_stat=1，word_num={data.get('word_num')}）")
                pending.remove(doc_id)
            elif stat == 2:
                fail = data.get("failInfo") or {}
                raise StepError(
                    f"文档 {doc_id} 向量化失败（embedding_stat=2）："
                    f"embedding_code={fail.get('embedding_code')}，"
                    f"embedding_msg={fail.get('embedding_msg') or '（服务端未返回原因）'}。"
                    "文档不可检索，不能算上传成功。"
                )
            else:
                print(f"      文档 {doc_id} 仍在处理中（embedding_stat={stat}）...")


def verify_retrieval(headers, knowledge_id, doc_ids, query):
    """实测检索：必须命中本次上传文档的切片才算验证通过，空结果一律按失败处理。"""
    print(f"[4/5] 检索验证：query={query!r}")
    for attempt in range(1, RETRIEVE_ATTEMPTS + 1):
        body = request_api(
            "POST", "/llm-application/open/knowledge/retrieve", headers,
            json={"query": query, "knowledge_ids": [knowledge_id],
                  "document_ids": doc_ids, "top_k": 5},
        )
        hits = body.get("data") or []
        ours = [h for h in hits if (h.get("metadata") or {}).get("doc_id") in doc_ids]
        if ours:
            top = ours[0]
            preview = " ".join((top.get("text") or "").split())[:80]
            print(f"      检索到 {len(ours)} 条来自本次上传文档的切片，"
                  f"最高分 {top.get('score')}，内容片段：{preview}")
            return
        note = f"（库内共返回 {len(hits)} 条，但都不是本次上传的文档）" if hits else "（data=[]，一条都没有）"
        print(f"      第 {attempt}/{RETRIEVE_ATTEMPTS} 次检索未命中本次文档{note}，"
              f"{RETRIEVE_INTERVAL} 秒后重试...")
        time.sleep(RETRIEVE_INTERVAL)
    # 兜底诊断：去掉 document_ids 过滤再查一次，把“整库检索不到”和“过滤参数问题”区分开
    unfiltered = request_api(
        "POST", "/llm-application/open/knowledge/retrieve", headers,
        json={"query": query, "knowledge_ids": [knowledge_id], "top_k": 5},
    )
    hits = unfiltered.get("data") or []
    if any((h.get("metadata") or {}).get("doc_id") in doc_ids for h in hits):
        print("      注意：document_ids 过滤未按预期生效，但不带过滤时能检索到本次上传的文档内容，判定可用。")
        return
    detail = (f"不带过滤时能检索到 {len(hits)} 条，但均来自其他文档"
              if hits else "不带 document_ids 过滤检索同样为空")
    raise StepError(
        f"检索验证失败：查询 {query!r} 连续 {RETRIEVE_ATTEMPTS} 次未检索到本次上传文档的任何内容"
        f"（{detail}）。上传和向量化状态虽然都显示成功，但实际检索不到内容——知识库不可用，不报告成功。"
    )


def main():
    print("=" * 62)
    print("智谱托管知识库：上传 faq.txt 并验证可检索")
    print("=" * 62)

    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    if not api_key:
        print("失败：未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key），无法调用接口。")
        return 1

    faq_path = Path(__file__).resolve().parent / "faq.txt"
    if not faq_path.is_file():
        print(f"失败：未找到 {faq_path}，请把 faq.txt 放到 main.py 同目录下再运行。")
        return 1
    try:
        first_line = next(
            line.strip() for line in faq_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    except UnicodeDecodeError:
        print(f"失败：{faq_path} 不是 UTF-8 编码的文本文件。")
        return 1
    except StopIteration:
        print(f"失败：{faq_path} 内容为空，没有可上传的问题。")
        return 1
    query = first_line[:100]  # 用文档里真实存在的一条问题做检索探针

    headers = {"Authorization": f"Bearer {api_key}"}
    knowledge_id = None
    ok = False
    try:
        knowledge_id = create_knowledge(headers)
        print(f"[1/5] 知识库创建成功：{knowledge_id}")

        doc_ids = upload_faq(headers, knowledge_id, faq_path)
        print(f"[2/5] faq.txt 上传成功：documentId={doc_ids}")

        wait_embedding(headers, doc_ids)

        verify_retrieval(headers, knowledge_id, doc_ids, query)
        ok = True
    except StepError as exc:
        print(f"\n失败：{exc}")
    except Exception:
        print("\n失败：发生未预期的异常：")
        print(traceback.format_exc())
    finally:
        if knowledge_id:
            print(f"[5/5] 清理：删除知识库 {knowledge_id}（含库内全部文档）...")
            try:
                request_api("DELETE", f"/llm-application/open/knowledge/{knowledge_id}", headers)
                print("      已删除。")
            except StepError as exc:
                ok = False  # 清理失败也不能瞒着，整体按失败退出
                print(f"      清理失败！知识库 {knowledge_id} 仍留在账号里，请到控制台手动删除：{exc}")
        else:
            print("[5/5] 清理：知识库未创建成功，无需清理。")

    if ok:
        print("\n成功：知识库已创建、faq.txt 已上传，且已实际检索到文档内容，确认可用；临时知识库已清理。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
