#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 contract.pdf 交给智谱 BigModel 的模型阅读并问答。

流程：
1. 调 POST /paas/v4/files 把 PDF 上传一次，拿到 file_id。
   注意 purpose 必须传 "user_data"：用 agent / code-interpreter 等 purpose
   上传同样能成功，但拿到的 file_id 在 chat/completions 里引用时会报
   1210「文件解析失败」；只有 user_data 上传的文件（支持
   pptx/ppt/docx/doc/xlsx/xls/pdf）才能被对话接口读取。
2. 三个问题各自发起一次独立的 chat/completions 请求，消息里只以
   {"type": "file", "file": {"file_id": ...}} 内容块引用同一个 file_id——
   请求体里只带 ID 字符串、不再携带文件内容，省带宽也省 token。

不在本地解析 PDF（不用 PyPDF2/pdfplumber/pypdf 等），全部交给平台。
API Key 从环境变量 ZHIPUAI_API_KEY 读取；已上传过的话可设置
ZHIPUAI_FILE_ID 跳过上传、直接复用旧 file_id。
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_MODEL = "glm-5.3-flash"  # 多模态模型，支持 content 数组里的 file 类型输入

PDF_NAME = "contract.pdf"
QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？",
]

UPLOAD_TIMEOUT = 300  # 扫描件可能较大，上传放宽超时
CHAT_TIMEOUT = 180


def api_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def check_response(resp, action):
    """统一检查 HTTP 状态码与响应体里的业务错误（如 1210）。"""
    try:
        body = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"{action}失败：HTTP {resp.status_code}，响应不是 JSON")
    error = body.get("error") if isinstance(body, dict) else None
    if error:
        raise RuntimeError(f"{action}失败：[{error.get('code')}] {error.get('message')}")
    resp.raise_for_status()
    return body


def find_contract_pdf():
    """定位 contract.pdf：优先环境变量/命令行参数，其次从 CWD 和脚本所在目录逐级向上找。"""
    override = os.environ.get("CONTRACT_PDF") or (sys.argv[1] if len(sys.argv) > 1 else None)
    candidates = [override] if override else []
    for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        d = start
        for _ in range(6):  # 向上最多找 6 层，兼容从子目录运行
            candidates.append(os.path.join(d, PDF_NAME))
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    searched = "\n  ".join(c for c in candidates if c)
    sys.exit(
        f"找不到 {PDF_NAME}。请把它放到脚本同目录（或任一上级目录），"
        f"或用 CONTRACT_PDF 环境变量 / 命令行参数指定路径。已尝试：\n  {searched}"
    )


def upload_pdf(api_key, pdf_path):
    """上传 PDF（purpose=user_data），返回 file_id。整个脚本只上传这一次。"""
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=api_headers(api_key),
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=UPLOAD_TIMEOUT,
        )
    body = check_response(resp, "上传文件")
    file_id = body.get("id")
    if not file_id:
        raise RuntimeError(f"上传响应里没有 id 字段：{body}")
    return file_id


def ask_about_contract(api_key, file_id, question):
    """带着同一个 file_id 问一个问题，返回模型回答。"""
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是合同审阅助手。请仅依据用户提供的合同文件内容回答，"
                "答案要具体，尽量引用合同中的关键原文。",
            },
            {
                "role": "user",
                # 多模态 content 数组：file 块只携带 file_id，不携带文件内容
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question},
                ],
            },
        ],
        # 不设 max_tokens：glm-5.3-flash 默认开启思考且思考 token 计入
        # max_tokens，预算给小了会 finish_reason=length、content 为空串。
    }
    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={**api_headers(api_key), "Content-Type": "application/json"},
        json=payload,
        timeout=CHAT_TIMEOUT,
    )
    body = check_response(resp, "对话请求")
    choice = body["choices"][0]
    content = (choice["message"].get("content") or "").strip()
    if not content:
        raise RuntimeError(
            f"模型返回空内容（finish_reason={choice.get('finish_reason')}）。"
            "若是 length，说明输出预算被思考 token 耗尽，请调大 max_tokens 后重试。"
        )
    return content


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）再运行。")

    pdf_path = find_contract_pdf()
    print(f"合同文件：{pdf_path}")

    # 支持复用已上传的文件，避免多轮提问反复上传
    file_id = os.environ.get("ZHIPUAI_FILE_ID", "").strip()
    if file_id:
        print(f"跳过上传，复用已有 file_id：{file_id}")
    else:
        file_id = upload_pdf(api_key, pdf_path)
        print(f"上传成功，file_id = {file_id}")
    print(f"（后续轮次可持续复用该 file_id，平台文件保留 30 天）")

    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n=== 问题 {i}：{question} ===")
        answer = ask_about_contract(api_key, file_id, question)
        print(answer)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        sys.exit(f"网络请求失败：{exc}")
    except RuntimeError as exc:
        sys.exit(f"错误：{exc}")
