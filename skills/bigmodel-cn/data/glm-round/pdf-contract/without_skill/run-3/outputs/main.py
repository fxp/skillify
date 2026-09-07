#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从合同扫描件 PDF 中抽取「合同编号」和「合同总金额」并打印到 stdout。

本地不做任何 PDF 解析(不依赖 PyPDF2 / pdfplumber / pypdf 等库):
PDF 的原始字节直接 Base64 成 data URL,作为 file 内容块随对话请求发给
智谱 BigModel 的多模态模型,由模型自己读取文件内容并完成抽取。

用法:
    ZHIPUAI_API_KEY=xxx python3 main.py [PDF 路径]
    不传路径时自动查找 contract.pdf(当前目录、脚本目录及其逐级上级目录,
    含上级目录下的 fixtures/ 子目录)。
"""

import base64
import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 支持文件输入的多模态模型(文件理解为视觉/多模态能力),可用环境变量覆盖
MODEL = os.environ.get("BIGMODEL_MODEL", "glm-5.3-flash")
PDF_NAME = "contract.pdf"
MAX_FILE_BYTES = 50 * 1024 * 1024  # 接口对单个 file 内容块的限制
TIMEOUT = 300  # 文件理解可能较慢,给足超时

PROMPT = (
    "请阅读用户提供的这份合同 PDF(扫描件转写稿),从中抽取两个字段:"
    "1) 合同编号;2) 合同总金额(保留原文中的数字、币种和单位,"
    "如大写金额与小写金额并存,请一并列出)。"
    '只输出一个 JSON 对象,不要输出任何解释文字或 Markdown 代码块,格式为 '
    '{"contract_no": "<合同编号,找不到则为null>", '
    '"total_amount": "<合同总金额,找不到则为null>"}。'
)


def find_pdf():
    """返回自动搜索到的 contract.pdf 路径,找不到返回 None。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), PDF_NAME),
        os.path.join(script_dir, PDF_NAME),
    ]
    # 逐级向上查找,同时兼顾上级目录下的 fixtures/contract.pdf
    ancestor = script_dir
    while True:
        ancestor = os.path.dirname(ancestor)
        candidates.append(os.path.join(ancestor, PDF_NAME))
        candidates.append(os.path.join(ancestor, "fixtures", PDF_NAME))
        if ancestor == os.path.dirname(ancestor):  # 已到根目录
            break
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def parse_answer(text):
    """从模型输出中解析 JSON 对象(容忍代码块包裹等噪声),失败返回 None。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def pick(obj, keys):
    for key in keys:
        value = obj.get(key)
        if value:
            return value
    return None


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 未设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else find_pdf()
    if not pdf_path or not os.path.isfile(pdf_path):
        print("错误: 找不到 %s,请将其放在当前目录或用参数指定路径" % PDF_NAME,
              file=sys.stderr)
        return 1

    size = os.path.getsize(pdf_path)
    if size > MAX_FILE_BYTES:
        print("错误: %s 大小 %.1fM,超过接口 50M 上限" % (pdf_path, size / 1048576.0),
              file=sys.stderr)
        return 1

    with open(pdf_path, "rb") as f:
        data_url = "data:application/pdf;base64," + \
            base64.b64encode(f.read()).decode("ascii")

    print("已读取 %s(%d 字节),交给模型 %s 读取…" % (pdf_path, size, MODEL),
          file=sys.stderr)

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "file_data": data_url,
                            "filename": os.path.basename(pdf_path),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }

    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={"Authorization": "Bearer " + api_key},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        print("错误: 请求 BigModel 失败: %s" % exc, file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print("错误: BigModel 返回 HTTP %d: %s" % (resp.status_code, resp.text[:500]),
              file=sys.stderr)
        return 1

    try:
        body = resp.json()
    except ValueError:
        print("错误: 响应不是 JSON: %s" % resp.text[:500], file=sys.stderr)
        return 1

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        print("错误: 响应中没有生成内容: %s"
              % json.dumps(body, ensure_ascii=False)[:500], file=sys.stderr)
        return 1

    result = parse_answer(content)
    if result is None:
        # 兜底:模型没按 JSON 格式回答时,原样输出其回答
        print(content.strip())
        return 0

    contract_no = pick(result, ("contract_no", "合同编号")) or "未找到"
    total_amount = pick(result, ("total_amount", "合同总金额")) or "未找到"
    print("合同编号: %s" % contract_no)
    print("合同总金额: %s" % total_amount)
    return 0


if __name__ == "__main__":
    sys.exit(main())
