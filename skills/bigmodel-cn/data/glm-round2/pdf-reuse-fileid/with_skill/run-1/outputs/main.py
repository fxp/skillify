#!/usr/bin/env python3
"""把同目录的 contract.pdf 交给智谱 BigModel 的模型阅读，然后连续问三个问题。

设计要点（为什么这样写）：
- PDF 只在开头上传一次：POST /paas/v4/files，purpose 必须传 "user_data"。
  chat/completions 里的 file 类型只认 user_data 上传的 file_id；用 agent /
  code-interpreter 等 purpose 上传虽然能成功，但拿那个 file_id 去引用时必定
  报 1210「文件解析失败」。
- 三个问题复用同一个 file_id：文件内容留在平台侧，后续请求只带引用，
  不再把整个文件塞进请求体；本地也完全不做 PDF 解析（无 PyPDF2/pdfplumber 等依赖）。
- 采用累积式多轮对话：文件引用只出现在第一条 user 消息里，后续追问是纯文本，
  每次请求在上一次 messages 的基础上追加，前缀逐字一致，也利于命中平台的
  隐式上下文缓存（命中部分按优惠价计费）。
- 模型用 glm-4.6v：支持文件理解的多模态模型，messages.content 支持 type=file。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
运行：python3 main.py
"""

import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
# 支持文件理解的多模态模型；换模型时注意必须支持 content 里的 type=file 输入
MODEL = os.environ.get("CHAT_MODEL", "glm-4.6v")
# 关键参数：file_id 只有以 purpose=user_data 上传才能被 chat 接口解析
PURPOSE = "user_data"
TIMEOUT = 300  # 带文件理解的对话响应可能较慢，超时放宽

QUESTIONS = [
    "这份合同的合同编号是什么？",
    "这份合同的合同总金额是多少？",
    "这份合同的违约金是怎么计算的？请依据合同原文条款说明。",
]


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def find_pdf():
    """定位 contract.pdf：环境变量指定 > 脚本同目录 > 当前目录 > 祖先目录下的 fixtures/。"""
    candidates = []
    if os.environ.get("CONTRACT_PDF"):
        candidates.append(Path(os.environ["CONTRACT_PDF"]))
    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir / "contract.pdf")
    candidates.append(Path.cwd() / "contract.pdf")
    candidates.extend(p / "fixtures" / "contract.pdf" for p in script_dir.parents)
    for path in candidates:
        if path.is_file():
            return path
    searched = "\n".join(f"  - {p}" for p in candidates)
    raise RuntimeError(f"找不到 contract.pdf，搜索过以下位置：\n{searched}")


def parse_response(resp, step):
    """统一校验响应：HTTP 状态 + 智谱业务错误体 {"error": {"code": ..., "message": ...}}。"""
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"{step}失败：响应不是 JSON：{resp.text[:300]}")
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise RuntimeError(f"{step}失败（业务错误码 {err.get('code')}）：{err.get('message')}")
    resp.raise_for_status()
    return data


def post_with_retry(url, tries=3, **kwargs):
    """对网络抖动 / 429 / 5xx 做简单重试；业务性 4xx（如 1210）直接抛出，不重试。"""
    last_error = None
    for attempt in range(1, tries + 1):
        try:
            resp = requests.post(url, timeout=TIMEOUT, **kwargs)
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            last_error = RuntimeError(f"HTTP {resp.status_code}：{resp.text[:200]}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < tries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"请求 {url} 重试 {tries} 次仍失败，最后一次错误：{last_error}")


def upload_pdf(pdf_path, api_key):
    """上传 PDF 换取 file_id。整个脚本只调用一次，后续所有提问都复用这个 id。"""
    pdf_bytes = pdf_path.read_bytes()  # 读一次成 bytes，重试时不会遇到文件句柄已读完的问题
    resp = post_with_retry(
        f"{BASE_URL}/paas/v4/files",
        headers=auth_headers(api_key),
        files={"file": (pdf_path.name, pdf_bytes, "application/pdf")},
        data={"purpose": PURPOSE},
    )
    data = parse_response(resp, "上传文件")
    file_id = data.get("id")
    if not file_id:
        raise RuntimeError(f"上传成功但响应里没有文件 id：{data}")
    return file_id


def chat(messages, api_key):
    resp = post_with_retry(
        f"{BASE_URL}/paas/v4/chat/completions",
        headers=auth_headers(api_key),
        json={"model": MODEL, "messages": messages},
    )
    data = parse_response(resp, "对话补全")
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"对话补全响应里没有 choices：{data}")
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content")
    if finish_reason not in (None, "stop"):
        raise RuntimeError(f"模型未正常结束（finish_reason={finish_reason}）：{choice!r}")
    if not content:
        raise RuntimeError(f"模型没有返回文本内容：{choice!r}")
    return content


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    # 第一步：上传一次，拿 file_id
    pdf_path = find_pdf()
    file_id = upload_pdf(pdf_path, api_key)
    print(f"已上传 {pdf_path.name} -> file_id = {file_id}")
    print("以下三个问题全部复用该 file_id，不再重复上传文件。\n")

    # 第二步：多轮追问。文件引用只出现在第一条 user 消息里，
    # 之后每轮把新的提问追加到 messages 末尾，文件靠历史里的 file_id 复用。
    messages = [
        {
            "role": "system",
            "content": "你是合同审阅助手，只依据用户提供的合同文件作答，编号、金额、条款务必与原文一致。",
        },
        {
            "role": "user",
            "content": [
                {"type": "file", "file": {"file_id": file_id}},
                {"type": "text", "text": QUESTIONS[0]},
            ],
        },
    ]

    for i, question in enumerate(QUESTIONS, start=1):
        if i > 1:
            # 追问只传纯文本，不重新携带文件内容
            messages.append({"role": "user", "content": question})
        answer = chat(messages, api_key)
        messages.append({"role": "assistant", "content": answer})
        print(f"[问题 {i}/{len(QUESTIONS)}] {question}")
        print(f"[回答] {answer}")
        print()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 统一转成简洁的错误输出与非零退出码
        print(f"运行失败：{exc}", file=sys.stderr)
        sys.exit(1)
