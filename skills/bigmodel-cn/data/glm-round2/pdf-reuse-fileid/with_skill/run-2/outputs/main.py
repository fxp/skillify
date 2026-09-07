#!/usr/bin/env python3
"""contract.pdf 合同问答：先上传一次拿 file_id，三个问题复用同一个 file_id。

流程：
1. POST /paas/v4/files 上传 contract.pdf（multipart，purpose=user_data——
   chat/completions 的 file 类型只认 user_data 上传的 file_id，
   用 agent/code-interpreter 等 purpose 上传的文件引用时会报 1210 文件解析失败）；
2. 每个问题单独调 POST /paas/v4/chat/completions，content 数组里用
   {"type": "file", "file": {"file_id": ...}} 引用同一个文件。
   全程不在本地解析 PDF，文件也只上传这一次（平台文件保留 30 天，
   后续更多轮提问继续复用这个 file_id 即可）。
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
CHAT_MODEL = "glm-5.3-flash"  # 原生多模态模型，支持 file 类型输入（PDF 文件理解）
UPLOAD_PURPOSE = "user_data"  # 必须 user_data，chat 接口才能通过 file_id 读取
TIMEOUT = 120  # 秒

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的合同总金额是多少？",
    "这份合同的违约金怎么算？",
]


def find_contract_pdf():
    """按 脚本同目录 -> 当前工作目录 -> 仓库 fixtures 目录 的顺序找 contract.pdf。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "contract.pdf"),
        os.path.abspath("contract.pdf"),
        os.path.abspath(
            os.path.join(script_dir, "..", "..", "..", "..", "fixtures", "contract.pdf")
        ),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("找不到 contract.pdf，已尝试: " + "; ".join(candidates))


def check(resp):
    """统一校验响应：HTTP 错误与响应体里的业务 error 字段都转成可读的异常。"""
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"API 返回了非 JSON 内容: {resp.text[:200]}")
    if not resp.ok or data.get("error"):
        raise RuntimeError(f"API 调用失败 [HTTP {resp.status_code}]: {data}")
    return data


def upload_pdf(api_key, path):
    """上传 PDF 一次，返回 file_id。"""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": UPLOAD_PURPOSE},
            timeout=TIMEOUT,
        )
    return check(resp)["id"]


def ask(api_key, file_id, question):
    """基于已上传的 file_id 提一个问题，返回模型回答文本。"""
    resp = requests.post(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "file": {"file_id": file_id}},
                        {"type": "text", "text": question},
                    ],
                }
            ],
            # glm-5.3 系列在标准端点强制思考（不能传 disabled），low 档≈轻量思考：
            # 合同字段抽取这类事实型问题用 low 更快更省 token
            "reasoning_effort": "low",
        },
        timeout=TIMEOUT,
    )
    data = check(resp)
    content = data["choices"][0]["message"].get("content")
    return (content or "").strip() or "(模型未返回内容)"


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    pdf_path = find_contract_pdf()
    print(f"PDF 路径: {pdf_path}")

    # 只上传这一次；后面所有轮次（含未来的提问）都复用这个 file_id
    file_id = upload_pdf(api_key, pdf_path)
    print(f"file_id: {file_id}\n")

    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题 {i}: {question}")
        print(f"回答 {i}: {ask(api_key, file_id, question)}")
        print()


if __name__ == "__main__":
    main()
