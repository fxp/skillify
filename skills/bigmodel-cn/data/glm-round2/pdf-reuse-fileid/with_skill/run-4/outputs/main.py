#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract.pdf 合同问答（智谱 BigModel / GLM）。

流程：
  1. 通过 POST /paas/v4/files 把 contract.pdf 上传一次（purpose=user_data——
     chat/completions 的 file 类型只认这个 purpose 上传的 file_id），拿到 file_id；
  2. 之后 3 个问题都在 messages 里以 {"type":"file","file":{"file_id":...}}
     引用同一个 file_id，文件不重复上传、不在本地解析 PDF；
  3. 问题与回答打印到 stdout。

依赖：仅 requests；API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_MODEL = "glm-5.3-flash"  # 原生多模态模型，支持 file 类型输入
PDF_NAME = "contract.pdf"
UPLOAD_TIMEOUT = 120
CHAT_TIMEOUT = 180
MAX_RETRIES = 3

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？请给出计算方式和触发条件。",
]


def find_pdf() -> Path:
    """定位 contract.pdf：命令行参数 > 脚本/工作目录及其上级目录（含 fixtures/）。"""
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser().resolve()
        if path.is_file():
            return path
        sys.exit(f"[错误] 找不到指定的文件：{path}")

    for root in (Path(__file__).resolve().parent, Path.cwd()):
        for base in (root, *list(root.parents)[:4]):
            for cand in (base / PDF_NAME, base / "fixtures" / PDF_NAME):
                if cand.is_file():
                    return cand
    sys.exit(
        f"[错误] 未找到 {PDF_NAME}。请把它与脚本放在同一目录，"
        f"或运行：python3 main.py /path/to/{PDF_NAME}"
    )


def call_with_retry(method: str, url: str, *, timeout: float = 60, **kwargs):
    """简单重试的 HTTP 调用（网络抖动 / 429 / 5xx），业务错误不重试。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            return resp
        except requests.RequestException as err:
            last_err = err
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    raise RuntimeError(f"请求 {url} 失败（已重试 {MAX_RETRIES} 次）：{last_err}")


def extract_error(resp) -> str:
    """把平台返回的业务错误（含 1210 这类参数错误）整理成可读文本。"""
    try:
        err = resp.json().get("error") or {}
        if err:
            return f"code={err.get('code')} message={err.get('message')}"
    except ValueError:
        pass
    return resp.text[:300]


def upload_pdf(api_key: str, pdf_path: Path) -> str:
    """上传 PDF 一次，返回 file_id（purpose 必须是 user_data）。"""
    with pdf_path.open("rb") as fh:
        resp = call_with_retry(
            "POST",
            f"{BASE_URL}/paas/v4/files",
            timeout=UPLOAD_TIMEOUT,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (pdf_path.name, fh, "application/pdf")},
            data={"purpose": "user_data"},
        )
    if not resp.ok:
        raise RuntimeError(f"上传失败：HTTP {resp.status_code} {extract_error(resp)}")
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"上传失败：{extract_error(resp)}")
    file_id = body.get("id")
    if not file_id:
        raise RuntimeError(f"上传响应里没有文件 id：{body}")
    return file_id


def ask(api_key: str, file_id: str, question: str) -> tuple:
    """基于同一个 file_id 提问，返回 (回答, usage)。"""
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是严谨的合同阅读助手，只依据用户提供的合同文件内容回答，不要编造。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question},
                ],
            },
        ],
        "reasoning_effort": "low",  # 事实抽取类问题用轻量思考，省 token
        "max_tokens": 1024,
    }
    resp = call_with_retry(
        "POST",
        f"{BASE_URL}/paas/v4/chat/completions",
        timeout=CHAT_TIMEOUT,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    if not resp.ok:
        raise RuntimeError(f"对话失败：HTTP {resp.status_code} {extract_error(resp)}")
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"对话失败：{extract_error(resp)}")
    choice = body["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason and finish_reason != "stop":
        print(f"[警告] finish_reason={finish_reason}", file=sys.stderr)
    content = (choice["message"].get("content") or "").strip()
    return content, body.get("usage") or {}


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("[错误] 请先设置环境变量 ZHIPUAI_API_KEY")

    pdf_path = find_pdf()
    print(f"PDF 文件：{pdf_path}")

    # 全程只上传这一次；后续所有轮次复用 file_id。
    file_id = upload_pdf(api_key, pdf_path)
    print(f"已上传（purpose=user_data），file_id = {file_id}")
    print(f"以下 {len(QUESTIONS)} 个问题均复用该 file_id，不再重复上传文件。\n")

    for idx, question in enumerate(QUESTIONS, 1):
        answer, usage = ask(api_key, file_id, question)
        print(f"问题 {idx}：{question}")
        print(f"回答 {idx}：{answer}")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        print(
            f"（tokens：prompt={usage.get('prompt_tokens', '?')}，"
            f"缓存命中={cached}，completion={usage.get('completion_tokens', '?')}）\n"
        )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, requests.RequestException) as err:
        print(f"[错误] {err}", file=sys.stderr)
        sys.exit(1)
