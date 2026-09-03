#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_extract.py

用智谱开放平台（bigmodel.cn / open.bigmodel.cn）的 GLM 大模型直接"阅读"本地 PDF
合同文件并抽取结构化关键信息（合同编号、甲方、乙方、金额），无需本地解析
PDF 文本的第三方库（如 PyPDF2 / pdfplumber）——PDF 文件本身被当作多模态输入，
交给模型端解析。

实现原理（均来自 bigmodel-cn 技能包 references/chat.md 与 references/files-batch.md，
并已用真实调用验证过关键坑点，不是凭空编的参数）：

1. 先调用 `POST /paas/v4/files` 上传 PDF，且 purpose 必须是 `user_data`。
   实测验证过：用 `agent`/`code-interpreter` 等其他 purpose 上传拿到的 file_id，
   放进 chat/completions 的 `file` 类型引用时会 100% 返回
   `{"error":{"code":"1210","message":"文件解析失败，请检查文件可访问性和格式"}}`。
   只有 `purpose=user_data` 上传的文件才能被 chat 接口的 `file` 类型正常解析。
   `user_data` 这个 purpose 本身只接受 pptx/ppt/docx/doc/xlsx/xls/pdf 格式，
   正好覆盖本脚本要处理的 PDF 合同文件。

2. 再调用 `POST /paas/v4/chat/completions`，把上一步拿到的 file_id 通过
   `{"type": "file", "file": {"file_id": ...}}` 放进多模态 user 消息的 content
   数组里，让模型直接读取 PDF 内容并按要求抽取关键信息。

   `file` 类型的多模态消息只有视觉模型（GLM-5.3-Flash / GLM-5V-Turbo / GLM-4.6V 等）
   支持，本脚本默认使用 `glm-5.3-flash`（智谱"看图/看视频 + 生成代码"的多模态旗舰，
   官方示例里也是用它演示多模态 content）。

   注意：视觉模型的请求体不支持 `response_format`（JSON 模式仅纯文本对话模型支持），
   所以这里改用 prompt 里明确约定 JSON 结构的方式让模型输出 JSON 文本，脚本再自行
   做健壮的 JSON 提取与解析（剥离可能出现的 ```json 代码块围栏、只取最外层的
   {...} 片段），并在解析失败时给出清晰的错误信息而不是崩溃。

3. 抽取完成后默认删除已上传的文件（`DELETE /paas/v4/files/{file_id}`），避免
   合同这类敏感文件长期留在智谱侧（默认最长也只保留 30 天，但用完即删更稳妥）；
   可用 --keep-file 保留。

用法：
    export ZHIPUAI_API_KEY="你的真实 API Key"
    python pdf_extract.py /path/to/contract.pdf
    python pdf_extract.py /path/to/contract.pdf --output result.json
    python pdf_extract.py /path/to/contract.pdf --model glm-4.6v --keep-file

API Key 从智谱开放平台控制台获取：
    https://bigmodel.cn/usercenter/proj-mgmt/apikeys
永远不要把 Key 硬编码进代码，本脚本只从环境变量 ZHIPUAI_API_KEY 读取。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Optional

import requests

# --------------------------------------------------------------------------
# 常量配置
# --------------------------------------------------------------------------

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
FILES_URL = f"{BASE_URL}/files"
CHAT_URL = f"{BASE_URL}/chat/completions"

# 上传给 chat/completions 用 file_id 引用时，必须用这个 purpose（详见模块顶部说明）。
FILE_UPLOAD_PURPOSE = "user_data"

# 支持 `file` 多模态输入的视觉模型；glm-5.3-flash 是官方文档里多模态示例默认使用的模型。
DEFAULT_MODEL = "glm-5.3-flash"

# user_data purpose 目前只接受这些格式（PDF 是本脚本的目标格式）。
SUPPORTED_EXTENSIONS = {".pdf"}

REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2.0

# 触发限流/过载、值得退避重试的业务错误码（见 references/errors-and-limits.md）。
RETRYABLE_ERROR_CODES = {"1302", "1305", "1308", "1310"}


class BigModelAPIError(RuntimeError):
    """智谱 API 返回的业务错误（4xx/5xx 且不值得重试，或重试耗尽后）。"""


# --------------------------------------------------------------------------
# 鉴权
# --------------------------------------------------------------------------


def get_api_key() -> str:
    """从环境变量读取 API Key，绝不硬编码进代码。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "未找到环境变量 ZHIPUAI_API_KEY。请先执行：\n"
            '    export ZHIPUAI_API_KEY="你的真实 API Key"\n'
            "API Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys"
        )
    return api_key


def auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# --------------------------------------------------------------------------
# 带退避重试的请求封装
# --------------------------------------------------------------------------


def _should_retry(resp: Optional[requests.Response], exc: Optional[Exception]) -> bool:
    """只对网络异常、5xx，以及限流/过载类业务错误码（1302/1305/1308/1310）重试；
    401/403/1210/1211 等配置或参数类错误重试没有意义，直接报错。"""
    if exc is not None:
        return True
    if resp is None:
        return False
    if resp.status_code >= 500:
        return True
    if resp.status_code == 429:
        return True
    if resp.status_code >= 400:
        try:
            code = str(resp.json().get("error", {}).get("code", ""))
        except (ValueError, AttributeError):
            return False
        return code in RETRYABLE_ERROR_CODES
    return False


def request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """对 429（账户限流 1302 / 平台过载 1305 / 用量上限 1308-1310）和 5xx 做指数退避重试，
    4xx 类配置/参数错误直接抛出，不做无意义重试。"""
    backoff = INITIAL_BACKOFF_SECONDS
    last_resp: Optional[requests.Response] = None
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(
                method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
            )
        except requests.RequestException as exc:  # 网络层异常
            last_exc, last_resp = exc, None
            if attempt == MAX_RETRIES or not _should_retry(None, exc):
                raise BigModelAPIError(f"请求 {url} 失败（网络异常）：{exc}") from exc
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.ok:
            return resp

        last_resp, last_exc = resp, None
        if attempt == MAX_RETRIES or not _should_retry(resp, None):
            _raise_for_bad_response(resp)

        time.sleep(backoff)
        backoff *= 2

    # 理论上不会走到这里，兜底处理。
    if last_resp is not None:
        _raise_for_bad_response(last_resp)
    raise BigModelAPIError(f"请求 {url} 重试耗尽，最后一次异常：{last_exc}")


def _raise_for_bad_response(resp: requests.Response) -> None:
    try:
        payload = resp.json()
        err = payload.get("error", {})
        code, message = err.get("code"), err.get("message")
    except (ValueError, AttributeError):
        code, message = None, resp.text[:500]
    raise BigModelAPIError(
        f"智谱 API 返回错误：HTTP {resp.status_code}, code={code}, message={message}"
    )


# --------------------------------------------------------------------------
# 第一步：上传 PDF 文件（purpose=user_data）
# --------------------------------------------------------------------------


def upload_pdf(pdf_path: str, api_key: str) -> str:
    """上传本地 PDF，返回 file_id。必须用 purpose=user_data，
    否则 chat/completions 引用该 file_id 时会报 1210 文件解析失败。"""
    filename = os.path.basename(pdf_path)
    with open(pdf_path, "rb") as f:
        resp = request_with_retry(
            "POST",
            FILES_URL,
            headers=auth_headers(api_key),
            files={"file": (filename, f, "application/pdf")},
            data={"purpose": FILE_UPLOAD_PURPOSE},
        )
    file_obj = resp.json()
    file_id = file_obj.get("id")
    if not file_id:
        raise BigModelAPIError(f"文件上传响应里没有 id 字段：{file_obj}")
    return file_id


def delete_file(file_id: str, api_key: str) -> None:
    """删除已上传文件，避免合同类敏感文件残留在智谱侧。失败仅告警，不影响主流程结果。"""
    try:
        request_with_retry(
            "DELETE",
            f"{FILES_URL}/{file_id}",
            headers=auth_headers(api_key),
        )
    except BigModelAPIError as exc:
        print(f"[警告] 清理已上传文件 {file_id} 失败（不影响抽取结果）：{exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# 第二步：调用 chat/completions，让模型直接读 PDF 并抽取结构化信息
# --------------------------------------------------------------------------

EXTRACTION_JSON_SCHEMA_HINT = """请仔细阅读这份 PDF 合同文件的完整内容，抽取以下关键信息，并且只以 JSON 对象格式输出，
不要输出 JSON 之外的任何解释性文字、不要用 ```json 代码块包裹，直接输出裸 JSON：

{
  "contract_no": "合同编号；找不到则填 null",
  "party_a": "甲方（全称，含公司主体信息）；找不到则填 null",
  "party_b": "乙方（全称，含公司主体信息）；找不到则填 null",
  "amount": "合同金额数值（阿拉伯数字，不含货币符号和千分位逗号，如 1000000.00）；找不到则填 null",
  "currency": "币种，如 CNY/USD；找不到或文件中未显式说明则填 null",
  "amount_in_words": "合同金额的中文大写或文字表述（如文件中有）；找不到则填 null",
  "confidence_notes": "抽取过程中的不确定说明，例如某字段是从上下文推断而非直接原文，没有则填空字符串"
}

如果同一份合同里出现多个金额（如总金额、分期金额、税额等），amount 填写合同约定的总金额/合同价款；
如果金额本身在原文中就是模糊或缺失的，对应字段填 null，不要编造数据。"""


def build_extraction_messages(file_id: str) -> list:
    return [
        {
            "role": "system",
            "content": (
                "你是专业的合同信息抽取助手，严谨、不臆造信息。"
                "只输出符合要求的 JSON，不输出多余内容。"
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACTION_JSON_SCHEMA_HINT},
                {"type": "file", "file": {"file_id": file_id}},
            ],
        },
    ]


def call_chat_completions(file_id: str, api_key: str, model: str) -> str:
    """调用 chat/completions，传入 file_id 引用刚上传的 PDF，返回模型原始文本回复。

    注意：这里用的是视觉模型（file 多模态类型的要求），视觉模型请求体不支持
    response_format 参数（JSON 模式仅纯文本模型支持），所以不传该参数，
    改为在 prompt 里显式约定 JSON 结构，返回后自行解析。
    """
    payload = {
        "model": model,
        "messages": build_extraction_messages(file_id),
        "temperature": 0.1,  # 抽取任务需要稳定、少发挥的输出
    }
    resp = request_with_retry(
        "POST",
        CHAT_URL,
        headers={**auth_headers(api_key), "Content-Type": "application/json"},
        json=payload,
    )
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise BigModelAPIError(f"chat/completions 响应结构异常：{data}") from exc


# --------------------------------------------------------------------------
# 第三步：从模型回复中稳健地提取 JSON
# --------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def parse_extraction_json(raw_text: str) -> dict:
    """模型理论上会按 prompt 要求直接输出裸 JSON，但仍可能：
    - 用 ```json ... ``` 包一层代码块
    - 在 JSON 前后夹带少量解释性文字
    这里做尽量健壮的提取，都失败时抛出异常并附上原始文本，方便排查而不是静默吞掉。
    """
    text = raw_text.strip()

    # 1) 直接尝试整体解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) 去掉 ```json ... ``` / ``` ... ``` 代码块围栏后再试
    stripped = _CODE_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3) 退而求其次：截取文本里第一个 { 到最后一个 } 之间的片段
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise BigModelAPIError(
        "无法从模型回复中解析出合法 JSON，请检查模型原始输出：\n" + raw_text
    )


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def extract_contract_info(
    pdf_path: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    keep_file: bool = False,
) -> dict:
    """端到端流程：上传 PDF -> 调用视觉模型读取并抽取 -> 解析 JSON -> （可选）清理文件。"""
    ext = os.path.splitext(pdf_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂只支持 PDF 文件，收到的扩展名是：{ext or '(无扩展名)'}")
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"文件不存在：{pdf_path}")

    file_id = upload_pdf(pdf_path, api_key)
    try:
        raw_content = call_chat_completions(file_id, api_key, model)
        extracted = parse_extraction_json(raw_content)
    finally:
        if not keep_file:
            delete_file(file_id, api_key)

    extracted["_meta"] = {
        "source_file": os.path.abspath(pdf_path),
        "model": model,
    }
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用智谱 GLM 大模型直接读取本地 PDF 合同文件，抽取合同编号/甲乙双方/金额等结构化信息。"
    )
    parser.add_argument("pdf_path", help="本地 PDF 合同文件路径")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"使用的智谱视觉模型（需支持 file 多模态输入），默认 {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--output",
        help="将结果 JSON 写入指定文件；不传则只打印到标准输出",
    )
    parser.add_argument(
        "--keep-file",
        action="store_true",
        help="抽取完成后保留已上传到智谱侧的文件（默认会自动删除）",
    )
    args = parser.parse_args()

    api_key = get_api_key()

    try:
        result = extract_contract_info(
            args.pdf_path, api_key, model=args.model, keep_file=args.keep_file
        )
    except (BigModelAPIError, ValueError, FileNotFoundError) as exc:
        print(f"抽取失败：{exc}", file=sys.stderr)
        sys.exit(1)

    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    print(output_text)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text + "\n")
        print(f"\n结果已写入：{os.path.abspath(args.output)}", file=sys.stderr)


if __name__ == "__main__":
    main()
