#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把同目录下的 contract.pdf 交给智谱 BigModel 的模型阅读，抽取并打印「合同编号」「合同总金额」。

- 本地不解析 PDF：整个文件以 base64 data URI 放入 chat/completions 的 file 输入，
  由视觉模型（默认 glm-4.6v）直接读文件（官方限制单文件 50M）。
- API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖 requests。
- 用法：python3 main.py
"""

import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 需选用支持文件输入的视觉模型，可用环境变量 BIGMODEL_MODEL 覆盖
MODEL = os.environ.get("BIGMODEL_MODEL", "glm-4.6v")
MAX_FILE_BYTES = 50 * 1024 * 1024  # 官方限制：file 输入单文件不超过 50M

# 查找 contract.pdf 的顺序：脚本所在目录 -> 脚本上级目录 -> 当前工作目录
SCRIPT_DIR = Path(__file__).resolve().parent
PDF_CANDIDATES = [
    SCRIPT_DIR / "contract.pdf",
    SCRIPT_DIR.parent / "contract.pdf",
    Path.cwd() / "contract.pdf",
]

PROMPT = (
    "请阅读附件中的合同 PDF，从中抽取以下两个字段：\n"
    "1. 合同编号（可能写作「合同编号」「编号」「Contract No.」等，通常在首页抬头处）；\n"
    "2. 合同总金额（合同总价款；若同时有大写和小写金额，请一并给出，保留原文写法和币种）。\n"
    "只输出一个 JSON 对象，不要输出任何解释文字或代码块标记，格式为：\n"
    '{"合同编号": "…", "合同总金额": "…"}\n'
    "若某字段在合同中确实不存在，对应值输出 null。"
)


def find_pdf() -> Path:
    for path in PDF_CANDIDATES:
        if path.is_file():
            return path
    searched = "、".join(str(p) for p in PDF_CANDIDATES)
    raise SystemExit(f"错误：未找到 contract.pdf（已查找：{searched}）")


def ask_model(api_key: str, pdf_path: Path) -> str:
    """把 PDF 原文件发给模型，返回模型的回答文本。"""
    pdf_bytes = pdf_path.read_bytes()
    if len(pdf_bytes) > MAX_FILE_BYTES:
        raise SystemExit(f"错误：{pdf_path} 超过 50M，超出 file 输入的大小限制")

    data_uri = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {"file_data": data_uri, "filename": pdf_path.name},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        "temperature": 0.1,
    }

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=300,
        )
    except requests.RequestException as exc:
        raise SystemExit(f"错误：请求 BigModel 接口失败：{exc}")

    if resp.status_code != 200:
        raise SystemExit(f"错误：API 返回 HTTP {resp.status_code}：{resp.text}")

    try:
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError):
        raise SystemExit(f"错误：无法解析 API 响应：{resp.text}")


def parse_answer(text: str):
    """从模型回答中解析 JSON；失败时返回 None（调用方退回打印原文）。"""
    text = text.strip()
    # 容错：剥掉可能的 ```json 代码块包裹
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def pick_field(data: dict, keyword: str):
    """按键名关键字（如「编号」「金额」）取值，容忍模型微调字段名。"""
    for key, value in data.items():
        if keyword in key:
            return value
    return None


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    pdf_path = find_pdf()
    print(f"# 模型 {MODEL} 正在读取 {pdf_path} ...", file=sys.stderr)

    answer = ask_model(api_key, pdf_path)
    data = parse_answer(answer)

    if data is None:
        print("警告：模型输出不是合法 JSON，以下为原始回答", file=sys.stderr)
        print(answer)
        sys.exit(1)

    contract_no = pick_field(data, "编号")
    total_amount = pick_field(data, "金额")
    print(f"合同编号: {contract_no if contract_no is not None else '未找到'}")
    print(f"合同总金额: {total_amount if total_amount is not None else '未找到'}")


if __name__ == "__main__":
    main()
