#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract.pdf 合同问答（智谱 BigModel / GLM）。

流程：
  1. 把 contract.pdf 通过 POST /paas/v4/files 上传到平台（purpose=user_data），
     拿到 file_id —— 整个脚本只上传这一次；
  2. 之后三个问题全部复用同一个 file_id，在 chat/completions 的 content 数组里
     以 {"type": "file", "file": {"file_id": ...}} 引用，不再重复传输文件内容，
     省带宽也省 token。

要点（来自 bigmodel-cn 技能包的实测结论，2026-09）：
  - 上传 purpose 必须是 user_data：用 agent / code-interpreter 等其他 purpose
    上传虽然能成功，但 chat 接口引用其 file_id 时会报 1210「文件解析失败」；
  - 本地不做任何 PDF 解析（不用 PyPDF2 / pdfplumber / pypdf 之类），
    文件内容完全由平台侧解析；
  - glm-5.3-flash 是原生多模态模型（图片/视频/文件输入）；在标准端点上
    思考强制开启（thinking.type=disabled 会报 1210），而思考 token 计入
    max_tokens，所以预算给足并检查 finish_reason，防止拿到空回答。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.3-flash"  # 原生多模态，支持文件输入
PDF_NAME = "contract.pdf"
QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的合同总金额是多少？",
    "这份合同的违约金怎么计算？",
]


def find_pdf():
    """在当前目录和脚本所在目录查找 contract.pdf。"""
    candidates = [
        os.path.join(os.getcwd(), PDF_NAME),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), PDF_NAME),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(f"找不到 {PDF_NAME}（已尝试：{'、'.join(candidates)}）")


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    return {"Authorization": f"Bearer {api_key}"}


def check(resp):
    """统一检查 HTTP 状态与业务错误体，返回解析后的 JSON。"""
    try:
        body = resp.json()
    except ValueError:
        resp.raise_for_status()
        sys.exit(f"错误：响应不是 JSON：{resp.text[:500]}")
    if not resp.ok:
        err = body.get("error") or body
        sys.exit(
            f"API 错误（HTTP {resp.status_code}）"
            f"code={err.get('code')} message={err.get('message')}"
        )
    return body


def upload_pdf(path):
    """上传 PDF，返回 file_id。purpose 必须是 user_data 才能被 chat 接口引用。"""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=auth_headers(),
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": "user_data"},
            timeout=300,
        )
    body = check(resp)
    file_id = body.get("id")
    if not file_id:
        sys.exit(f"上传失败：响应里没有文件 id：{body}")
    return file_id


def ask(file_id, question):
    """复用同一个 file_id 问一个问题，返回模型回答文本。"""
    payload = {
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
        # 思考 token 计入 max_tokens（glm-5.3-flash 标准端点强制思考），
        # 预算给足，避免 finish_reason=length 导致空回答
        "max_tokens": 32768,
    }
    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={**auth_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    body = check(resp)
    choice = body["choices"][0]
    finish_reason = choice.get("finish_reason")
    answer = ((choice.get("message") or {}).get("content") or "").strip()
    if finish_reason != "stop":
        sys.exit(
            f"回答异常：finish_reason={finish_reason}"
            "（若为 length，说明 max_tokens 预算不足）"
        )
    return answer


def main():
    pdf_path = find_pdf()
    file_id = upload_pdf(pdf_path)
    print(f"已上传 {pdf_path}，file_id={file_id}（三个问题复用，不重复上传）")
    print()
    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题 {i}：{question}")
        print(f"答案：{ask(file_id, question)}")
        print()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    except requests.RequestException as exc:
        sys.exit(f"网络/接口调用失败：{exc}")
