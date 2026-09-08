#!/usr/bin/env python3
"""把 contract.pdf 交给智谱 BigModel 阅读，然后连问三个合同问题。

接入要点（来自 bigmodel-cn 接入手册与官方文档 docs.bigmodel.cn）：
- 文件只上传一次：POST /paas/v4/files，purpose 必须传 user_data。
  用 agent / code-interpreter 等 purpose 上传虽然能成功，但对话里引用
  file_id 时会报 1210「文件解析失败」——user_data 是唯一被 chat 认可的用途。
- 对话端点在 content 数组里用 {"type":"file","file":{"file_id":...}} 引用
  文件；后续每一轮提问都复用同一个 file_id，不再重复上传或内联文件内容。
- 模型选 glm-5.3-flash：原生多模态，官方「文件理解」示例所用模型。
- 不设 max_tokens：思考 token 也计入该预算，给小了会 finish_reason=length、
  content 为空的静默失败，因此这里改为检查 finish_reason 是否正常。
- 不在本地解析 PDF（不用 PyPDF2/pdfplumber/pypdf），解析全部由平台完成。
"""

import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
UPLOAD_URL = f"{BASE_URL}/paas/v4/files"
CHAT_URL = f"{BASE_URL}/paas/v4/chat/completions"
MODEL = "glm-5.3-flash"

QUESTIONS = [
    "这份合同的合同编号是什么？请直接给出编号。",
    "这份合同的总金额是多少？请给出金额和币种。",
    "这份合同的违约金是怎么计算的？请说明计算方式。",
]


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    return {"Authorization": f"Bearer {api_key}"}


def find_pdf():
    """在脚本所在目录及其上级目录里找 contract.pdf。"""
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        p = d / "contract.pdf"
        if p.is_file():
            return p
    sys.exit("错误：找不到 contract.pdf（已在脚本目录及上级目录查找）")


def upload_pdf(headers, pdf_path):
    """上传 PDF，返回可被对话接口引用的 file_id。只调用一次。"""
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            UPLOAD_URL,
            headers=headers,
            files={"file": (pdf_path.name, f, "application/pdf")},
            data={"purpose": "user_data"},  # 必须是 user_data，否则对话引用时报 1210
            timeout=300,
        )
    if not resp.ok:
        sys.exit(f"上传失败 HTTP {resp.status_code}: {resp.text}")
    file_id = resp.json().get("id")
    if not file_id:
        sys.exit(f"上传响应中没有文件 id: {resp.text}")
    return file_id


def ask(headers, file_id, question):
    """带着同一个 file_id 提问；每一轮都复用它，不重新传文件。"""
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
    }
    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=300)
    if not resp.ok:
        sys.exit(f"对话请求失败 HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        sys.exit(f"对话请求返回业务错误: {data['error']}")
    choice = data["choices"][0]
    answer = (choice["message"].get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    if not answer:
        # 典型成因：思考 token 耗尽输出预算（finish_reason=length）
        sys.exit(f"模型返回空内容（finish_reason={finish_reason}）")
    return answer


def main():
    headers = auth_headers()
    pdf_path = find_pdf()

    file_id = upload_pdf(headers, pdf_path)
    print(f"已上传 {pdf_path.name}，file_id = {file_id}（后续问题全部复用它）")
    print()

    for i, question in enumerate(QUESTIONS, 1):
        print(f"问题{i}：{question}")
        print(f"回答：{ask(headers, file_id, question)}")
        print()


if __name__ == "__main__":
    main()
