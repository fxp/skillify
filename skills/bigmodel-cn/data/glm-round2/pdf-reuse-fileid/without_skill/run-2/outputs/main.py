#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向智谱 BigModel 询问 contract.pdf 合同内容（三问三答）。

做法（官方 v4 HTTP 接口，仅依赖 requests，不做本地 PDF 解析）：
  1. POST {API_BASE}/files            multipart 上传一次，purpose=agent（支持 pdf，单文件 <=20M），
                                      响应 JSON 的 "id" 字段即 file_id；
  2. POST {API_BASE}/chat/completions 三个问题各自发起一轮对话，每轮只在 messages.content 里
                                      引用同一个 file_id（{"type":"file","file":{"file_id":...}}），
                                      不再重复上传、也不把文件内容 base64 塞进请求，省带宽省 token。

API Key 从环境变量 ZHIPUAI_API_KEY 读取；运行：python3 main.py [contract.pdf 可选路径]
"""

import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.environ.get(
    "BIGMODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
).rstrip("/")
# 文件输入需要视觉系模型；官方"文件理解"示例即用 glm-5.3-flash
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3-flash")
UPLOAD_PURPOSE = "agent"  # 上传用途：agent 支持 pdf/docx/xlsx 等，单文件 <=20M
MAX_RETRIES = 3
TIMEOUT = (10, 300)  # (连接超时, 读超时) 秒

QUESTIONS = [
    "这份合同的合同编号是什么？请直接给出编号。",
    "这份合同的总金额是多少？请给出具体金额和币种。",
    "这份合同的违约金是怎么计算的？请概述违约金条款的计算方式。",
]


def die(msg):
    print("[错误] %s" % msg, file=sys.stderr)
    sys.exit(1)


def find_contract_pdf():
    """按 命令行参数 > 环境变量 > 常见位置 的顺序找 contract.pdf。"""
    hints = []
    if len(sys.argv) > 1:
        hints.append(Path(sys.argv[1]).expanduser())
    env = os.environ.get("CONTRACT_PDF")
    if env:
        hints.append(Path(env).expanduser())
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "contract.pdf",  # 与脚本同目录
        script_dir.parent / "contract.pdf",  # 脚本上一级（工作目录）
        Path.cwd() / "contract.pdf",
        Path.cwd().parent / "contract.pdf",
    ]
    if len(script_dir.parents) > 3:  # 本工作区 fixtures 布局的兜底路径
        candidates.append(script_dir.parents[3] / "fixtures" / "contract.pdf")
    for p in hints + candidates:
        if p.is_file():
            return p
    if hints:
        die("指定的文件不存在：%s" % hints[0])
    die("未找到 contract.pdf，请把它放到脚本同目录，或用 `python3 main.py <路径>` 指定")


def request_with_retry(session, method, url, api_key, **kwargs):
    """带 Authorization 头发请求；5xx/429/网络错误退避重试，4xx 直接报错退出。"""
    headers = {"Authorization": "Bearer %s" % api_key}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.request(
                method, url, headers=headers, timeout=TIMEOUT, **kwargs
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = "HTTP %s: %s" % (resp.status_code, resp.text[:300])
            elif resp.status_code >= 400:
                die("请求失败 HTTP %s：%s" % (resp.status_code, resp.text[:500]))
            else:
                return resp
        except requests.RequestException as exc:
            last_err = str(exc)
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
    die("重试 %d 次后仍失败：%s" % (MAX_RETRIES, last_err))


def upload_pdf(session, api_key, pdf_path):
    """上传 PDF 一次，返回 file_id，供后续所有提问复用。"""
    content = pdf_path.read_bytes()  # <=20M，直接读入内存以便失败重试
    resp = request_with_retry(
        session,
        "POST",
        API_BASE + "/files",
        api_key,
        files={"file": (pdf_path.name, content, "application/pdf")},
        data={"purpose": UPLOAD_PURPOSE},
    )
    payload = resp.json()
    file_id = payload.get("id") or payload.get("file_id")
    if not file_id:
        die("上传成功但响应中没有文件 id：%s" % payload)
    return file_id


def ask_with_file(session, api_key, file_id, question):
    """带着同一个 file_id 提问，返回 (回答文本, 本轮 total_tokens)。"""
    payload = {
        "model": MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    # 复用已上传文件的 file_id，本轮不再传文件本体
                    {"type": "file", "file": {"file_id": file_id}},
                    {"type": "text", "text": question},
                ],
            }
        ],
    }
    resp = request_with_retry(
        session, "POST", API_BASE + "/chat/completions", api_key, json=payload
    )
    data = resp.json()
    try:
        answer = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        die("响应结构异常，取不到回答：%s" % str(data)[:500])
    usage = data.get("usage") or {}
    return answer, usage.get("total_tokens")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")

    pdf_path = find_contract_pdf()
    session = requests.Session()

    print("[准备] 上传 %s（%d 字节）" % (pdf_path, pdf_path.stat().st_size), file=sys.stderr)
    file_id = upload_pdf(session, api_key, pdf_path)
    print("[准备] file_id=%s，三问复用，不再重复上传" % file_id, file=sys.stderr)
    print("[准备] 模型：%s" % MODEL, file=sys.stderr)

    for i, question in enumerate(QUESTIONS, 1):
        answer, total_tokens = ask_with_file(session, api_key, file_id, question)
        print("问题 %d：%s" % (i, question))
        print("回答 %d：%s" % (i, answer))
        if total_tokens is not None:
            print("（本轮消耗 %s tokens）" % total_tokens)
        print()


if __name__ == "__main__":
    main()
