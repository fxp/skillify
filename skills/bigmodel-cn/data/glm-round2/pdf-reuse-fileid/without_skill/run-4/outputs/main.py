#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract.pdf 合同问答（智谱 BigModel 平台版）

流程：
  1. 把本地 contract.pdf 通过「文件上传」接口一次性上传到平台，拿到 file_id；
  2. 之后三轮提问全部复用同一个 file_id —— 每轮只在 content 里带一个
     {"type": "file", "file": {"file_id": ...}} 引用，不再把文件重新塞进请求，
     省带宽也省 token（后面还要反复问很多轮，同样只需要这一个 file_id）；
  3. 全程不做本地 PDF 解析（不引入 PyPDF2 / pdfplumber / pypdf 等库），
     只把文件二进制交给平台，由平台的多模态模型阅读。

依赖：仅 requests。
运行：ZHIPUAI_API_KEY=<你的Key> python3 main.py
"""

import os
import sys
import time

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
FILES_URL = f"{API_BASE}/files"
CHAT_URL = f"{API_BASE}/chat/completions"

# 文件理解用的多模态模型（官方“文件理解”示例同款，原生支持 图片/视频/文件 输入）
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3-flash")

PDF_NAME = "contract.pdf"

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？",
]

HTTP_TIMEOUT = 300  # 单次请求超时（秒）
MAX_RETRIES = 3     # 限流/服务器错误时的重试次数


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("环境变量 ZHIPUAI_API_KEY 未设置，请先：export ZHIPUAI_API_KEY=<你的API Key>")
    return {"Authorization": f"Bearer {api_key}"}


def check_response(resp, action):
    if resp.status_code // 100 == 2:
        return
    die(f"{action}失败：HTTP {resp.status_code} {resp.text[:500]}")


def find_pdf():
    """在当前目录、脚本所在目录及其上级目录里定位 contract.pdf（只定位，不解析）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates, seen = [], set()
    for d in (os.getcwd(), script_dir,
              os.path.dirname(script_dir),
              os.path.dirname(os.path.dirname(script_dir))):
        if d and d not in seen:
            seen.add(d)
            candidates.append(d)
    for d in candidates:
        path = os.path.join(d, PDF_NAME)
        if os.path.isfile(path):
            return path
    die(f"未找到 {PDF_NAME}，已在以下目录搜索过：{', '.join(candidates)}")


def upload_pdf(path, headers):
    """把 PDF 一次性上传到平台，返回 file_id（后续所有提问都复用它）。"""
    with open(path, "rb") as f:
        resp = requests.post(
            FILES_URL,
            headers=headers,
            files={"file": (os.path.basename(path), f, "application/pdf")},
            data={"purpose": "agent"},  # 平台文件托管，支持 pdf，可在对话中按 file_id 引用
            timeout=HTTP_TIMEOUT,
        )
    check_response(resp, "上传文件")
    file_id = resp.json().get("id")
    if not file_id:
        die(f"上传成功但响应里没有文件 id：{resp.text[:500]}")
    return file_id


def ask(file_id, question, headers):
    """带同一个 file_id 提问一次；对限流/服务器错误做简单退避重试。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    # 只传 file_id 引用，不重传文件内容
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": f"请阅读附件合同并回答：{question}"},
                ],
            }
        ],
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(CHAT_URL, headers=headers,
                                 json=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                die(f"提问时网络异常：{exc}")
            time.sleep(2 * attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            time.sleep(2 * attempt)
            continue
        check_response(resp, "对话补全")
        data = resp.json()
        choices = data.get("choices") or [{}]
        answer = (choices[0].get("message") or {}).get("content") or ""
        if not answer:
            die(f"模型没有返回内容：{data}")
        return answer.strip()


def main():
    headers = auth_headers()
    pdf_path = find_pdf()

    print(f"合同文件：{pdf_path}")
    print("正在把 PDF 上传到 BigModel 平台（整个流程只上传这一次）...")
    file_id = upload_pdf(pdf_path, headers)
    print(f"已获得 file_id：{file_id}")
    print(f"使用模型：{MODEL}")
    print()

    for i, question in enumerate(QUESTIONS, 1):
        print("=" * 60)
        print(f"【问题 {i}】{question}")
        answer = ask(file_id, question, headers)
        print(f"【回答 {i}】{answer}")
        print()

    print("=" * 60)
    print(f"三轮提问均复用同一个 file_id（{file_id}），文件没有重复上传。")


if __name__ == "__main__":
    main()
