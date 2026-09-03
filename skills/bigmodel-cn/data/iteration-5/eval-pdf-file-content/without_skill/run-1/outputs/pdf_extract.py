#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_extract.py

使用智谱（Zhipu / BigModel）大模型直接读取 PDF 合同文件内容，
抽取关键信息（合同编号、甲方、乙方、金额等），输出结构化 JSON。

思路：不在本地用 PyPDF2 / pdfplumber 等库解析 PDF 文本，而是把 PDF
原文件上传到智谱开放平台（purpose=file-extract），由平台服务端完成
文件内容解析/抽取；再把解析出的文本作为上下文喂给 GLM 大模型做结构化
信息抽取。整个过程只用标准库 + requests 直接调用 HTTP 接口，不依赖
官方 zhipuai SDK，也不依赖任何本地 PDF 解析库。

用法:
    export ZHIPU_API_KEY="你的APIKey"   # 通常形如 "{key_id}.{key_secret}"
    python pdf_extract.py /path/to/contract.pdf

依赖:
    pip install requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

import requests

# ---------------------------------------------------------------------------
# 接口配置
# ---------------------------------------------------------------------------

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
FILES_ENDPOINT = f"{API_BASE}/files"
CHAT_ENDPOINT = f"{API_BASE}/chat/completions"

# 用于文档理解 / 信息抽取的模型。
# 合同类 PDF 往往篇幅较长，glm-4-long 是智谱面向长文本/长文档场景优化的模型，
# 上下文窗口大，比较适合“整份合同一次性喂给模型”的场景。
# 如果账号未开通 glm-4-long，可以按需替换为 "glm-4-plus" 或 "glm-4-air" 等。
MODEL_NAME = "glm-4-long"

# 文件上传时的 purpose 参数。
#
# 智谱开放平台 /files 接口的 purpose 支持多个取值，语义大致是：
#   - "file-extract": 上传文件后，由平台服务端直接完成文件内容解析
#     （PDF/Word/PPT 等），随后可以通过 /files/{file_id}/content
#     拿到解析出的文本，再把这段文本拼进对话上下文交给大模型分析。
#     这正对应本任务“不想自己在本地解析 PDF，让模型/平台直接读文件”的诉求，
#     且是针对“单次、一次性分析这一份文件”的场景，不需要额外建知识库。
#   - "retrieval": 用于构建可供模型检索的知识库（Knowledge/RAG），
#     更适合“长期维护一批文档，反复检索问答”的场景，对本脚本这种
#     一次性单文件抽取来说是过度设计。
#   - "batch" / "fine-tune": 分别用于批量推理任务、模型微调数据集，
#     与“读取合同内容”这个目标完全无关。
#
# 综上，本脚本使用 purpose="file-extract"。
FILE_PURPOSE = "file-extract"

TIMEOUT = 120  # 秒


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------


def get_api_key() -> str:
    """从环境变量读取智谱 API Key（占位符：请勿把真实 key 写死在代码里）。"""
    api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not api_key:
        print(
            "错误: 未设置环境变量 ZHIPU_API_KEY。\n"
            "请先执行: export ZHIPU_API_KEY='你的智谱API Key'",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


def build_headers(api_key: str, content_type: Optional[str] = None) -> Dict[str, str]:
    """
    构造鉴权请求头。

    注意：智谱官方 SDK（zhipuai）内部会把形如 "{key_id}.{key_secret}"
    的 API Key 转换成一个短期 JWT（HS256 签名，payload 含 api_key / exp /
    timestamp），再放进 Authorization 头。目前开放平台的 REST 接口也
    documented 支持直接把原始 API Key 作为 Bearer token 使用，写法更简单，
    本脚本采用这种方式。如果你的账号/接口版本要求必须传 JWT，
    需要自行实现 JWT 签发（用 hmac + hashlib.sha256 + base64，
    "." 前半部分作为 key id 放入 payload 的 api_key 字段，
    "." 后半部分作为 HMAC 签名密钥），替换掉这里的 Authorization 值即可。
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


# ---------------------------------------------------------------------------
# 第一步：上传 PDF 文件
# ---------------------------------------------------------------------------


def upload_pdf(file_path: str, api_key: str) -> str:
    """上传 PDF 文件到智谱开放平台（purpose=file-extract），返回 file_id。"""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        files = {"file": (filename, f, "application/pdf")}
        data = {"purpose": FILE_PURPOSE}
        resp = requests.post(
            FILES_ENDPOINT,
            headers=build_headers(api_key),
            files=files,
            data=data,
            timeout=TIMEOUT,
        )
    resp.raise_for_status()
    result = resp.json()

    file_id = result.get("id")
    if not file_id:
        raise RuntimeError(f"上传文件成功但响应中未找到 file_id，原始响应: {result}")
    return file_id


# ---------------------------------------------------------------------------
# 第二步：拉取平台解析出的文件文本内容
# ---------------------------------------------------------------------------


def fetch_file_content(file_id: str, api_key: str) -> str:
    """
    获取平台已解析出的 PDF 文本内容。
    对应接口: GET /files/{file_id}/content
    """
    url = f"{FILES_ENDPOINT}/{file_id}/content"
    resp = requests.get(url, headers=build_headers(api_key), timeout=TIMEOUT)
    resp.raise_for_status()
    result = resp.json()

    # 不同接口版本返回结构可能略有差异，这里做一个尽量宽容的兼容解析，
    # 而不是假设一种固定 schema。
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # 形如 [{"type": "text", "text": "..."}] 的多段内容
            texts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    texts.append(str(item["text"]))
                elif isinstance(item, str):
                    texts.append(item)
            if texts:
                return "\n".join(texts)
        if isinstance(result.get("text"), str):
            return result["text"]

    # 兜底：拿不到预期字段时，把整个响应体转成字符串，至少不丢信息，
    # 方便排查接口返回结构是否发生变化。
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 第三步：调用大模型做结构化信息抽取
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """你是一名专业的合同信息抽取助手。下面是一份合同 PDF 被解析出的全部文本内容，
请仔细阅读，并从中提取以下关键信息，严格以 JSON 对象格式输出，不要输出任何 JSON 以外的文字、
不要使用 Markdown 代码块包裹：

{{
  "合同编号": "合同编号，若未找到填 null",
  "甲方": "甲方（Party A）全称，若未找到填 null",
  "乙方": "乙方（Party B）全称，若未找到填 null",
  "金额": "合同金额（含币种及大小写原文；若有多笔金额，填写主要的合同总金额），若未找到填 null",
  "签订日期": "合同签订日期，若未找到填 null"
}}

合同文本内容如下：
-----
{document_text}
-----
"""


def extract_contract_info(document_text: str, api_key: str) -> Dict[str, Any]:
    """调用 GLM 模型，从合同文本中抽取结构化关键信息。"""
    prompt = EXTRACTION_PROMPT.format(document_text=document_text)

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        # 部分 GLM 模型支持强制输出合法 JSON；如果账号/模型不支持该参数，
        # 报错时可去掉这一项，退回“纯文本输出 + 下面的兜底解析”。
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(
        CHAT_ENDPOINT,
        headers=build_headers(api_key, content_type="application/json"),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()

    try:
        raw_answer = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"未能从模型响应中解析出内容，原始响应: {result}") from exc

    try:
        return json.loads(raw_answer)
    except json.JSONDecodeError:
        # 模型偶尔可能在 JSON 前后夹带说明文字，尝试截取花括号部分再解析一次
        start = raw_answer.find("{")
        end = raw_answer.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw_answer[start : end + 1])
            except json.JSONDecodeError:
                pass
        # 实在解析不了，就把模型原始输出一并返回，方便人工排查
        return {"_raw_model_output": raw_answer}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def process_pdf(file_path: str) -> Dict[str, Any]:
    api_key = get_api_key()

    print(f"[1/3] 正在上传文件到智谱开放平台: {file_path}", file=sys.stderr)
    file_id = upload_pdf(file_path, api_key)
    print(f"      上传成功，file_id = {file_id}", file=sys.stderr)

    print("[2/3] 正在获取服务端解析出的文件文本内容...", file=sys.stderr)
    document_text = fetch_file_content(file_id, api_key)
    print(f"      获取到文本长度: {len(document_text)} 字符", file=sys.stderr)

    print(f"[3/3] 正在调用 {MODEL_NAME} 模型抽取关键信息...", file=sys.stderr)
    info = extract_contract_info(document_text, api_key)

    return {
        "file_path": file_path,
        "file_id": file_id,
        "model": MODEL_NAME,
        "extracted_info": info,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用智谱 GLM 大模型从本地 PDF 合同中抽取关键信息（合同编号/甲乙双方/金额）",
    )
    parser.add_argument("pdf_path", help="本地 PDF 合同文件路径")
    args = parser.parse_args()

    try:
        result = process_pdf(args.pdf_path)
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            body = exc.response.text
        print(f"HTTP 请求失败: {exc}\n响应内容: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"处理失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
