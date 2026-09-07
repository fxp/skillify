#!/usr/bin/env python3
"""contract.pdf 合同问答（智谱 BigModel 开放平台）。

流程：
1. 从环境变量 ZHIPUAI_API_KEY 读取密钥；
2. 把脚本同目录下的 contract.pdf 通过文件上传接口（POST /paas/v4/files，
   purpose=file-extract）上传一次，拿到 file_id；
3. 之后三个问题（合同编号 / 总金额 / 违约金）全部在 messages 里以
   {"type": "file", "file": {"file_id": ...}} 的方式引用同一个 file_id，
   不重传文件，也不在本地解析 PDF（无 PyPDF2/pdfplumber/pypdf 依赖）；
4. 问答结果打印到 stdout，进度/提示信息走 stderr。

跨脚本复用：后续多轮提问时可设置环境变量 ZHIPUAI_FILE_ID=<id>，
脚本会跳过上传直接复用该文件。模型可用 ZHIPUAI_MODEL 覆盖（默认 glm-4.6v）。

参考文档：
- 上传文件：https://docs.bigmodel.cn/api-reference/文件-api/上传文件
- 对话补全（content 里的 file/file_id 字段）：
  https://docs.bigmodel.cn/api-reference/模型-api/对话补全
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
FILES_URL = f"{BASE_URL}/files"
CHAT_URL = f"{BASE_URL}/chat/completions"

MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6v")  # 文件理解需要视觉系模型
PDF_PATH = Path(__file__).resolve().parent / "contract.pdf"

MAX_ATTEMPTS = 3  # 网络异常 / 限流 / 5xx 的重试次数
UPLOAD_TIMEOUT = 300  # 秒，上传给足时间
CHAT_TIMEOUT = 180

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的总金额是多少？",
    "这份合同的违约金是怎么计算的？请给出金额/比例和触发条件。",
]


def fail(msg):
    return SystemExit(f"[错误] {msg}")


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def call_api(send, what):
    """执行一次 HTTP 请求；对网络异常、429、5xx 做指数退避重试。"""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = send()
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                raise fail(f"{what} 网络请求失败：{exc}") from exc
        else:
            # 4xx（鉴权/参数类）不重试，直接交给 ensure_ok 报错
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            if attempt == MAX_ATTEMPTS:
                return resp
        delay = 2 ** attempt
        print(f"[重试] {what}（第 {attempt} 次失败，{delay}s 后重试）", file=sys.stderr)
        time.sleep(delay)
    raise fail(f"{what} 请求未能完成")  # 理论上到不了这里


def ensure_ok(resp, what):
    if 200 <= resp.status_code < 300:
        return
    try:
        detail = json.dumps(resp.json(), ensure_ascii=False)
    except ValueError:
        detail = resp.text[:500]
    raise fail(f"{what} 失败：HTTP {resp.status_code} {detail}")


def upload_pdf(api_key, path):
    """上传 PDF 一次，返回 file_id。每次重试都重新打开文件句柄。"""

    def send():
        with path.open("rb") as fh:
            return requests.post(
                FILES_URL,
                headers=auth_headers(api_key),
                files={"file": (path.name, fh, "application/pdf")},
                data={"purpose": "file-extract"},  # 文档理解/问答用途
                timeout=UPLOAD_TIMEOUT,
            )

    resp = call_api(send, "上传 contract.pdf")
    ensure_ok(resp, "上传 contract.pdf")
    file_id = (resp.json() or {}).get("id")
    if not file_id:
        raise fail(f"上传返回里没有 id 字段：{resp.text[:500]}")
    return file_id


def ask(api_key, file_id, filename, question):
    """基于已上传的 file_id 提一个问题，返回模型回答文本。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    # 文件只以 file_id 引用：不重传、不把正文塞进 prompt
                    {"type": "file", "file": {"file_id": file_id, "filename": filename}},
                    {"type": "text", "text": question},
                ],
            }
        ],
        "thinking": {"type": "disabled"},  # 事实型抽取，无需深度思考
        "max_tokens": 2048,
        "temperature": 0.1,
    }
    resp = call_api(
        lambda: requests.post(
            CHAT_URL, headers=auth_headers(api_key), json=payload, timeout=CHAT_TIMEOUT
        ),
        f"提问“{question}”",
    )
    ensure_ok(resp, "提问")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise fail(f"提问返回里没有 choices：{json.dumps(data, ensure_ascii=False)[:500]}")
    content = (choices[0].get("message") or {}).get("content", "")
    if isinstance(content, list):  # 多模态返回可能是分段文本
        content = "\n".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return str(content).strip()


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise fail("请先设置环境变量 ZHIPUAI_API_KEY")

    if not PDF_PATH.is_file():
        raise fail(f"找不到合同文件：{PDF_PATH}")

    # 已有 file_id 时直接复用，省掉重复上传
    file_id = os.environ.get("ZHIPUAI_FILE_ID", "").strip()
    if file_id:
        print(f"[复用] 使用环境变量指定的 file_id：{file_id}", file=sys.stderr)
    else:
        size_kb = PDF_PATH.stat().st_size / 1024
        print(f"[上传] {PDF_PATH.name}（{size_kb:.1f} KB）...", file=sys.stderr)
        file_id = upload_pdf(api_key, PDF_PATH)
        print(f"[上传] 完成，file_id = {file_id}", file=sys.stderr)
        print(f"[提示] 后续运行可 export ZHIPUAI_FILE_ID={file_id} 免上传", file=sys.stderr)

    print(f"[模型] {MODEL}", file=sys.stderr)
    for i, question in enumerate(QUESTIONS, 1):
        answer = ask(api_key, file_id, PDF_PATH.name, question)
        print(f"问题 {i}：{question}")
        print(f"回答：{answer}")
        print()
    print("[完成] 共 3 个问题，文件只上传了一次。", file=sys.stderr)


if __name__ == "__main__":
    main()
