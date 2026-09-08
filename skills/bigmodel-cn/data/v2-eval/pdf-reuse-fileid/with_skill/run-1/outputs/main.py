#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 读合同 PDF 并连续提问。

流程：
  1. 把 contract.pdf 通过 POST /paas/v4/files 上传一次，拿到 file_id（purpose 必须为
     user_data，否则 chat 里引用时会报 1210 文件解析失败）；
  2. 后续三个问题全部复用同一个 file_id，以 {"type": "file", "file": {"file_id": ...}}
     的形式放进 messages，不在本地解析 PDF、也不重复上传。

依赖：仅 requests + 标准库。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_URL = f"{BASE_URL}/paas/v4/chat/completions"
FILES_URL = f"{BASE_URL}/paas/v4/files"

MODEL = "glm-5.3-flash"  # 官方文档确认支持 file 类型内容输入的多模态模型

PDF_NAME = "contract.pdf"

QUESTIONS = [
    "这份合同的合同编号是什么？请直接给出编号原文。",
    "这份合同的总金额是多少？请给出金额（含单位），如有大写与小写金额请一并列出。",
    "这份合同的违约金是怎么计算的？请引用合同相关条款，说明计算方式或比例。",
]


def log(msg: str) -> None:
    """进度信息走 stderr，保证 stdout 只有问答结果，便于管道处理。"""
    print(msg, file=sys.stderr, flush=True)


def find_pdf() -> str:
    """在脚本目录、当前目录及其向上最多 5 级父目录里找 contract.pdf。"""
    candidates = []
    for start in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        cur = start
        for _ in range(5):
            path = os.path.join(cur, PDF_NAME)
            if path not in candidates:
                candidates.append(path)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f"找不到 {PDF_NAME}，请把它放到脚本同目录（或任一父目录）下，或修改 PDF_NAME。"
    )


def get_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)
    return key


def check_response(resp: requests.Response, what: str) -> dict:
    """统一报错：优先展示平台返回的 error.code / error.message。"""
    if not resp.ok:
        raise RuntimeError(f"{what} 失败：HTTP {resp.status_code} {resp.text[:500]}")
    body = resp.json()
    if isinstance(body.get("error"), dict):
        err = body["error"]
        raise RuntimeError(f"{what} 失败：{err.get('code')} {err.get('message')}")
    return body


def upload_pdf(api_key: str, pdf_path: str) -> str:
    """上传一次，返回 file_id。purpose 必须是 user_data 才能在 chat/completions 里引用。"""
    log(f"上传 {pdf_path} …")
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            FILES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=300,
        )
    body = check_response(resp, "上传文件")
    file_id = body["id"]
    log(f"上传成功：file_id={file_id}（{body.get('bytes')} 字节，平台保留 30 天，可跨脚本复用）")
    return file_id


def ask(api_key: str, file_id: str, question: str) -> str:
    """带同一个 file_id 提一个问题，返回回答文本。"""
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "file": {"file_id": file_id}},
                        {"type": "text", "text": question},
                    ],
                }
            ],
            # 不设 max_tokens：思考模型会把推理 token 计入预算，设小了会拿到空回答
        },
        timeout=300,
    )
    body = check_response(resp, "对话补全")
    choice = body["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason != "stop":
        # finish_reason=length 说明输出预算被思考耗尽；sensitive 为内容拦截；等
        log(f"警告：finish_reason={finish_reason}，回答可能不完整")
    content = choice["message"].get("content") or ""
    return content.strip()


def main() -> None:
    api_key = get_api_key()
    pdf_path = find_pdf()

    # 关键：整个文件只上传这一次，三个问题全部复用这个 file_id
    file_id = upload_pdf(api_key, pdf_path)

    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题 {i}：{question}")
        answer = ask(api_key, file_id, question)
        print(f"回答 {i}：{answer}")
        print()
        log(f"第 {i}/3 个问题完成（复用 file_id={file_id}，未重新上传）")


if __name__ == "__main__":
    main()
