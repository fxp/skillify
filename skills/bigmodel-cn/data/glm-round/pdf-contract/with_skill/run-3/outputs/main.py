#!/usr/bin/env python3
"""从合同 PDF 中抽取「合同编号」和「合同总金额」。

刻意不做任何本地 PDF 解析（不使用 PyPDF2 / pdfplumber / pypdf 等库把文字抠出来）：
本地只把原始 PDF 字节做 Base64 传输编码，通过智谱 BigModel 对话补全接口的
多模态 file 输入（file_data 内联）把整个文件交给 glm-5.3-flash，
由模型自己读文件并给出抽取结果。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py [contract.pdf 的路径]   # 不传参数时自动查找
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CHAT_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3-flash"  # 多模态旗舰；官方文档"文件理解"示例即用此模型，支持 file 类型输入
PDF_MIME = "application/pdf"
REQUEST_TIMEOUT = 300  # 扫描件识别 + 生成需要时间，超时放宽
MAX_RETRIES = 3  # 仅对 429 / 5xx 做指数退避重试

PROMPT = (
    "请阅读附件中的合同 PDF，抽取以下两个字段：\n"
    "1. 合同编号\n"
    "2. 合同总金额（保留原文写法；若同时有大写金额和数字金额，请一并给出）\n"
    "只输出一个 JSON 对象，不要输出任何解释文字或 Markdown 代码块，格式：\n"
    '{"合同编号": "…", "合同总金额": "…"}\n'
    "若某字段在合同中确实不存在，对应值输出空字符串。"
)


def find_pdf() -> Path:
    """定位 contract.pdf：命令行参数 > 脚本/当前目录 > 逐级向上（含 fixtures/ 子目录）。"""
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"指定的 PDF 不存在: {path}")
        return path

    script_dir = Path(__file__).resolve().parent
    search_bases = [Path.cwd(), script_dir, *script_dir.parents, *Path.cwd().parents]
    for base in search_bases:
        for candidate in (base / "contract.pdf", base / "fixtures" / "contract.pdf"):
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        "未找到 contract.pdf：请把它放在脚本同目录下，或用 `python3 main.py <路径>` 指定。"
    )


def chat_extract(api_key: str, pdf_path: Path) -> dict:
    """把 PDF 以 file_data 内联发给模型，返回 chat/completions 的完整响应 JSON。"""
    pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "file_data": f"data:{PDF_MIME};base64,{pdf_b64}",
                            "filename": pdf_path.name,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        # glm-5.3-flash 在标准端点强制思考（传 thinking disabled 会报 1210），
        # 简单抽取任务用 low 档即可：实测接近不思考，更快更省
        "reasoning_effort": "low",
        "max_tokens": 2048,
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code < 400:
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"API 业务错误 {data['error'].get('code')}: {data['error'].get('message')}")
            return data
        last_error = f"HTTP {resp.status_code}: {resp.text.strip()[:500]}"
        # 429（限流/过载）与 5xx 才值得重试；4xx 属于鉴权/参数问题，重试无意义
        if resp.status_code != 429 and resp.status_code < 500:
            break
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)  # 指数退避，避免加重限流
    raise RuntimeError(f"API 请求失败: {last_error}")


def parse_answer(data: dict) -> tuple:
    """从响应里取出模型输出并解析成 (合同编号, 合同总金额)。"""
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应中没有 choices: {json.dumps(data, ensure_ascii=False)[:500]}")
    content = (choices[0].get("message") or {}).get("content") or ""

    # 视觉模型输出可能夹带 <think>…</think> 与 <|begin_of_box|> 边界标签，先清掉
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "").strip()

    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError(f"模型未返回 JSON，原始输出:\n{content}")
    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型返回的 JSON 无法解析（{exc}），原始输出:\n{content}") from exc

    contract_no = result.get("合同编号") or result.get("contract_no") or ""
    total_amount = result.get("合同总金额") or result.get("total_amount") or ""
    if not contract_no and not total_amount:
        raise ValueError(f"未能抽取到任何字段，模型原始输出:\n{content}")
    return contract_no, total_amount


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    try:
        pdf_path = find_pdf()
        print(f"已找到合同文件: {pdf_path}", file=sys.stderr)  # 诊断信息走 stderr，保持 stdout 干净
        resp = chat_extract(api_key, pdf_path)
        contract_no, total_amount = parse_answer(resp)
    except (OSError, RuntimeError, ValueError, requests.RequestException) as exc:
        print(f"抽取失败: {exc}", file=sys.stderr)
        return 1

    print(f"合同编号: {contract_no}")
    print(f"合同总金额: {total_amount}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
