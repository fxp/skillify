#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 contract.pdf 并向智谱 BigModel 连续提问三个问题。

流程：
1. 通过文件接口把 contract.pdf 上传一次，拿到 file_id；
2. 后续每个问题都在 messages 里以 {"type": "file", "file": {"file_id": ...}}
   引用同一个 file_id（文档：单文件 ≤ 50M，file_id 来自 /files 上传接口），
   不再重复上传文件、也不在本地解析 PDF；
3. 把三个问题的答案依次打印到 stdout。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
运行：python3 main.py
"""

import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# glm-5.3-flash 支持文件(file_id)输入的多模态模型；纯文本模型不支持 file 内容块
MODEL = "glm-5.3-flash"
PDF_NAME = "contract.pdf"
# 上传 purpose 依次尝试：文档枚举里 agent / user_data / code-interpreter 均允许 pdf，
# 平台侧校验规则可能随版本变化，故 400 时按序降级重试
UPLOAD_PURPOSES = ("agent", "user_data", "code-interpreter")
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
TIMEOUT = 300  # 秒

QUESTIONS = (
    "这份合同的合同编号是什么？请直接给出编号。",
    "这份合同的合同总金额是多少？请给出具体金额（含币种和大写金额，如有）。",
    "这份合同的违约金是怎么算的？请说明计算方式并引用相关条款。",
)


def find_pdf() -> Path:
    """按 脚本所在目录 → 当前工作目录 的顺序查找 contract.pdf。"""
    candidates = [
        Path(__file__).resolve().parent / PDF_NAME,
        Path.cwd() / PDF_NAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    searched = "、".join(str(p) for p in candidates)
    raise SystemExit(f"找不到 {PDF_NAME}，已尝试：{searched}")


def error_text(resp: requests.Response) -> str:
    """把错误响应压缩成一行可读信息。"""
    try:
        err = resp.json().get("error") or {}
        detail = f"{err.get('code', '')} {err.get('message', '')}".strip()
        if not detail:
            detail = resp.text[:300]
    except ValueError:
        detail = resp.text[:300]
    return f"HTTP {resp.status_code}: {detail}"


def upload_pdf(session: requests.Session, pdf_path: Path) -> str:
    """上传 PDF 一次，返回 file_id（供所有后续提问复用）。"""
    last_error = "未知错误"
    for purpose in UPLOAD_PURPOSES:
        with pdf_path.open("rb") as fh:
            resp = session.post(
                f"{BASE_URL}/files",
                files={"file": (pdf_path.name, fh, "application/pdf")},
                data={"purpose": purpose},
                timeout=TIMEOUT,
            )
        if resp.status_code == 200:
            file_id = (resp.json() or {}).get("id")
            if file_id:
                print(f"文件上传成功：file_id={file_id}（purpose={purpose}），"
                      "后续提问复用该 file_id，不再重复上传。")
                return file_id
            last_error = f"HTTP 200 但响应缺少 id：{resp.text[:300]}"
        else:
            last_error = error_text(resp)
            if resp.status_code != 400:
                break  # 非 purpose 相关的错误（鉴权、限流等），换 purpose 无意义
    raise SystemExit(f"文件上传失败：{last_error}")


def ask_question(session: requests.Session, file_id: str, question: str) -> str:
    """带着同一个 file_id 向模型提问，返回回答文本。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    # 只传 file_id，不重复传文件内容
                    {"type": "file", "file": {"file_id": file_id, "filename": PDF_NAME}},
                    {"type": "text", "text": question},
                ],
            }
        ],
    }
    url = f"{BASE_URL}/chat/completions"
    for attempt in range(2):  # 瞬时错误重试一次
        resp = session.post(url, json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            break
        if resp.status_code in RETRYABLE_STATUS and attempt == 0:
            time.sleep(3)
            continue
        raise SystemExit(f"对话请求失败：{error_text(resp)}")
    else:  # 理论上到不了这里，保险起见
        raise SystemExit(f"对话请求失败：{error_text(resp)}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError):
        raise SystemExit(f"解析对话响应失败：{str(data)[:500]}")


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请先设置环境变量 ZHIPUAI_API_KEY（智谱 BigModel API Key）。")

    pdf_path = find_pdf()
    print(f"待读取文件：{pdf_path}（{pdf_path.stat().st_size / 1024:.1f} KB）")

    with requests.Session() as session:
        session.headers.update({"Authorization": f"Bearer {api_key}"})
        file_id = upload_pdf(session, pdf_path)  # 只上传这一次
        print()
        for index, question in enumerate(QUESTIONS, start=1):
            answer = ask_question(session, file_id, question)
            print(f"问题 {index}：{question}")
            print(f"回答：{answer}")
            print("-" * 60)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        raise SystemExit(f"网络请求异常：{exc}")
    except KeyboardInterrupt:
        sys.exit(130)
