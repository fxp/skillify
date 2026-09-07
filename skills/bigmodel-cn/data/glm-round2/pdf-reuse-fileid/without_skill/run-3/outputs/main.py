#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 contract.pdf（合同扫描件）交给智谱 BigModel 的模型阅读，并连续提出三个问题。

做法：
1. 先调用文件上传接口（POST /paas/v4/files）把 PDF 传到平台，拿到 file_id；
2. 之后每个问题都在 chat/completions 的 content 里引用同一个 file_id——
   全程只上传一次文件，后续多轮提问复用，不重复传输文件、也不把文件内容
   塞进请求体，省带宽也省 token；
3. 三个问题（合同编号 / 总金额 / 违约金）的答案依次打印到 stdout。

PDF 完全由平台解析（多模态模型直接读文件），本地不做任何 PDF 解析。
依赖：仅 requests。
运行：ZHIPUAI_API_KEY=你的Key python3 main.py [contract.pdf路径]
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
FILES_URL = BASE_URL + "/files"
CHAT_URL = BASE_URL + "/chat/completions"

# 多模态模型，支持在 content 中以 file 类型输入文件（官方文档文件问答示例所用）
MODEL = "glm-5.3-flash"

# 上传接口的 purpose：旧版指南用 file-extract，新版接口枚举为
# batch / code-interpreter / agent / voice-clone-input，文档未明确对话补全
# 引用 file_id 时的取值要求，因此按兼容顺序依次尝试，成功即用。
UPLOAD_PURPOSES = ("file-extract", "agent", "code-interpreter")

PDF_NAME = "contract.pdf"
TIMEOUT = (10, 300)  # (连接超时, 读取超时)，秒；上传与长回答都留足时间

QUESTIONS = (
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？",
)

SYSTEM_PROMPT = (
    "你是合同阅读助手。请只依据用户消息中提供的合同文件内容回答，"
    "给出准确、简洁的中文答案；合同中没有的信息请直接说明未找到。"
)


def fail(message):
    print(f"[错误] {message}", file=sys.stderr)
    sys.exit(1)


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("请先设置环境变量 ZHIPUAI_API_KEY")
    return {"Authorization": f"Bearer {api_key}"}


def find_pdf():
    """按 命令行参数 > 当前目录 > 脚本所在目录 > 脚本上级目录 的顺序找合同文件。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        PDF_NAME,
        os.path.join(script_dir, PDF_NAME),
        os.path.normpath(os.path.join(script_dir, os.pardir, PDF_NAME)),
    ]
    if len(sys.argv) > 1:
        candidates.insert(0, sys.argv[1])
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    fail(f"未找到 {PDF_NAME}；请在合同所在目录运行本脚本，或把文件路径作为第一个参数传入")


def check_chat_response(resp, question):
    """对话接口的统一响应检查：HTTP 状态码 + 平台返回的 error 字段。"""
    if resp.status_code in (401, 403):
        fail(f"提问「{question}」失败：鉴权不通过（HTTP {resp.status_code}），请检查 ZHIPUAI_API_KEY")
    if not resp.ok:
        fail(f"提问「{question}」失败：HTTP {resp.status_code} {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        fail(f"提问「{question}」失败：响应不是 JSON：{resp.text[:300]}")
    error = data.get("error")
    if error:
        fail(f"提问「{question}」失败：{error.get('code')} {error.get('message')}")
    return data


def upload_pdf(headers, pdf_path):
    """上传 PDF 到平台并返回 file_id。只在脚本开始时调用一次，后续所有问题复用。"""
    last_message = "所有 purpose 均未返回结果"
    with open(pdf_path, "rb") as fh:
        for purpose in UPLOAD_PURPOSES:
            fh.seek(0)
            files = {"file": (os.path.basename(pdf_path), fh, "application/pdf")}
            try:
                resp = requests.post(
                    FILES_URL,
                    headers=headers,
                    data={"purpose": purpose},
                    files=files,
                    timeout=TIMEOUT,
                )
            except requests.RequestException as exc:
                fail(f"上传文件请求异常：{exc}")
            if resp.status_code in (401, 403):
                fail(f"上传文件失败：鉴权不通过（HTTP {resp.status_code}），请检查 ZHIPUAI_API_KEY")
            try:
                data = resp.json()
            except ValueError:
                data = {}
            file_id = data.get("id")
            if resp.ok and file_id:
                return file_id
            # 其余错误多与参数有关，记录原因后换下一个 purpose 再试
            detail = data.get("error") or resp.text
            last_message = f"purpose={purpose} HTTP {resp.status_code} {str(detail)[:200]}"
    fail(f"上传文件失败（已尝试 purpose={'/'.join(UPLOAD_PURPOSES)}）：{last_message}")


def ask(headers, file_id, question):
    """向模型提问。content 中只携带 file_id 引用，不重复传输文件本身。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question},
                ],
            },
        ],
    }
    try:
        resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        fail(f"提问「{question}」请求异常：{exc}")
    data = check_chat_response(resp, question)
    choices = data.get("choices") or []
    if not choices:
        fail(f"提问「{question}」失败：响应中没有 choices：{str(data)[:300]}")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    return content if content else "（模型未返回内容，请重试）"


def main():
    headers = auth_headers()
    pdf_path = find_pdf()
    size_mb = os.path.getsize(pdf_path) / 1024.0 / 1024.0
    print(f"合同文件：{pdf_path}（{size_mb:.2f} MB）")

    # 只上传这一次；三个问题（以及之后的更多轮）都复用同一个 file_id
    file_id = upload_pdf(headers, pdf_path)
    print(f"文件已上传，file_id = {file_id}（以下问题均复用该 file_id，不再重复上传文件）")
    print("=" * 60)

    for index, question in enumerate(QUESTIONS, 1):
        answer = ask(headers, file_id, question)
        print(f"问题{index}：{question}")
        print(f"答案{index}：{answer}")
        if index < len(QUESTIONS):
            print("-" * 60)


if __name__ == "__main__":
    main()
