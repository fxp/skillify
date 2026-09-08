#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract.pdf 合同问答脚本（智谱 BigModel）。

流程：
1. 把脚本同目录下的 contract.pdf 上传到智谱开放平台，拿到 file_id（只上传一次）；
2. 用同一个 file_id 连问三个问题，每轮请求里只带 file_id 引用，
   不重复上传、也不把文件内容内联进请求，省带宽也省 token。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
运行：python3 main.py
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# file 类型输入挂在视觉模型请求（ChatCompletionVisionRequest）下，
# 官方"文件理解"示例用的就是 glm-5.3-flash，纯文本模型（如 glm-5.3）不适用。
MODEL = "glm-5.3-flash"
PDF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract.pdf")

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么算的？请按条款原文说明计算方式。",
]


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")
    return key


def check_error(resp, what):
    """智谱的错误统一放在 body 的 error 字段里，HTTP 状态码不一定反映真实失败原因，两边都查。"""
    if resp.status_code >= 400:
        sys.exit(f"{what} 失败：HTTP {resp.status_code}，响应：{resp.text}")
    body = resp.json()
    if isinstance(body, dict) and body.get("error"):
        err = body["error"]
        sys.exit(f"{what} 失败：[{err.get('code')}] {err.get('message')}")
    return body


def upload_pdf(path):
    """上传 PDF，返回 file_id。

    purpose 必须传 user_data：用 agent / code-interpreter 等其他 purpose
    上传同样能成功，但拿到的 file_id 在 chat/completions 里引用时会报
    1210「文件解析失败」。user_data 只接受 pdf/doc(x)/xls(x)/ppt(x)，
    本地不做任何解析，文件原样交给平台。
    """
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/files",
            headers={"Authorization": f"Bearer {get_api_key()}"},
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=300,
        )
    body = check_error(resp, "上传 PDF")
    file_id = body["id"]
    print(f"[上传成功] {os.path.basename(path)} -> file_id = {file_id}")
    return file_id


def ask(file_id, question):
    """带着同一个 file_id 问一个问题，返回模型回答。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    # 复用已上传文件的 file_id，请求体里只有这一个字符串引用
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": f"请阅读附件合同，只依据合同内容回答：{question}"},
                ],
            }
        ],
        # 思考 token 也计入 max_tokens，glm-5.3-flash 在标准端点强制开启思考，
        # 预算给足，避免 finish_reason=length 导致 content 被截空
        "max_tokens": 8192,
        "reasoning_effort": "low",  # 简单事实抽取类问题，压低思考开销
    }
    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {get_api_key()}"},
        json=payload,
        timeout=180,
    )
    body = check_error(resp, f"提问「{question}」")
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        print("[警告] 回答因 max_tokens 截断，可能不完整", file=sys.stderr)
    return (choice["message"]["content"] or "").strip()


def main():
    if not os.path.isfile(PDF_PATH):
        sys.exit(f"错误：找不到合同文件 {PDF_PATH}")
    if not PDF_PATH.lower().endswith(".pdf"):
        sys.exit(f"错误：{PDF_PATH} 不是 PDF 文件")

    file_id = upload_pdf(PDF_PATH)  # 全程只上传这一次，后续轮次全部复用
    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n=== 问题 {i}：{question} ===")
        print(ask(file_id, question))


if __name__ == "__main__":
    main()
