#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 的多模态模型阅读 contract.pdf（合同扫描件），
抽取「合同编号」和「合同总金额」并打印到 stdout。

- PDF 原文件以 base64 Data URL 的形式放进 chat/completions 的 file 内容块，
  由模型自己读文件；全程不在本地解析 PDF（不使用 PyPDF2 / pdfplumber / pypdf 等）。
- 仅依赖 requests；API Key 从环境变量 ZHIPUAI_API_KEY 读取。
- 运行方式：python3 main.py

接口：POST https://open.bigmodel.cn/api/paas/v4/chat/completions
模型：glm-5.3-flash（视觉模型，支持文本/图片/视频/文件输入，
      官方「文件理解」示例所用模型；file 块三选一：file_id / file_url / file_data）
"""

import base64
import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3-flash"
PDF_NAME = "contract.pdf"
MAX_FILE_BYTES = 50 * 1024 * 1024  # 接口单文件大小上限 50MB

PROMPT = (
    "你是一名合同信息抽取助手。请阅读附件中的合同 PDF 扫描件，抽取以下两项信息：\n"
    "1. 合同编号\n"
    "2. 合同总金额（保留原文的币种、数字与写法，例如「人民币壹拾万元整（¥100,000.00）」）\n"
    "要求：只依据文件内容作答，不要臆造；若某项在文件中不存在，其值填「未找到」。\n"
    "只输出一个 JSON 对象，不要任何解释或代码块，格式：\n"
    '{"合同编号": "...", "合同总金额": "..."}'
)


def find_pdf():
    """在当前目录、脚本所在目录逐级向上查找 contract.pdf（含 fixtures/ 子目录）。"""
    starts = [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]
    seen = set()
    for start in starts:
        dir_ = start
        for _ in range(6):  # 最多向上 6 层
            if dir_ in seen:
                break
            seen.add(dir_)
            for cand in (os.path.join(dir_, PDF_NAME), os.path.join(dir_, "fixtures", PDF_NAME)):
                if os.path.isfile(cand):
                    return cand
            parent = os.path.dirname(dir_)
            if parent == dir_:
                break
            dir_ = parent
    return None


def parse_fields(text):
    """从模型回复中解析 JSON（容忍 ```json 围栏或前后多余文字）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=<你的APIKey>")

    pdf_path = find_pdf()
    if pdf_path is None:
        sys.exit(f"错误：找不到 {PDF_NAME}（已在当前目录、脚本目录及其上级目录、fixtures/ 子目录中查找）")

    size = os.path.getsize(pdf_path)
    if size > MAX_FILE_BYTES:
        sys.exit(f"错误：{pdf_path} 大小 {size} 字节，超过接口单文件 50MB 上限")
    print(f"[*] 使用 {pdf_path}（{size} 字节），调用 {MODEL} 直接阅读 PDF 原文件…", file=sys.stderr)

    with open(pdf_path, "rb") as f:
        file_data = "data:application/pdf;base64," + base64.b64encode(f.read()).decode("ascii")

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {"file_data": file_data, "filename": PDF_NAME},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=600,
        )
    except requests.RequestException as exc:
        sys.exit(f"错误：请求 BigModel 接口失败：{exc}")

    if resp.status_code != 200:
        sys.exit(f"错误：接口返回 HTTP {resp.status_code}：{resp.text[:500]}")

    try:
        message = resp.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError):
        sys.exit(f"错误：无法解析接口响应：{resp.text[:500]}")

    content = (message.get("content") or "").strip()
    if not content:
        sys.exit("错误：模型返回内容为空")

    fields = parse_fields(content)
    if fields is None:
        # 兜底：模型未按 JSON 输出时，把原文直接打印出来
        print(content)
        return

    print(f"合同编号: {fields.get('合同编号', '未找到')}")
    print(f"合同总金额: {fields.get('合同总金额', '未找到')}")


if __name__ == "__main__":
    main()
