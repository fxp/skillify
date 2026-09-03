#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_feedback.py

从一段客户反馈文本中，使用智谱 GLM-5.3 模型抽取结构化信息：
    - name        : 客户姓名（字符串，未提及时为 null）
    - issue_type  : 问题类型（枚举）
    - urgency     : 紧急程度（枚举）

设计目标：调用方拿到的返回值必须能直接 json.loads() 解析成功，且严格符合
预先定义好的 JSON Schema，不需要在业务代码里再写正则 / 容错解析逻辑。

实现思路（双保险）：
    1. 主要保证：调用智谱 GLM 的 OpenAI 兼容 Chat Completions 接口时，
       显式传入 `response_format = {"type": "json_schema", "json_schema": {...}, "strict": true}`。
       这会让模型在解码阶段做结构化约束（constrained decoding），
       从模型侧就保证输出是「合法 JSON + 符合给定 Schema」。
    2. 兜底保证：即便如此，仍然用 `jsonschema` 对返回结果做一次本地校验
       （模型/网关版本差异、灰度特性开关等都可能导致 strict 模式退化成
       普通 json_object 模式），校验失败或 JSON 解析失败时自动重试
       （带指数退避），重试次数耗尽后抛出明确异常，绝不把脏数据交给下游。

使用方式：
    export ZHIPU_API_KEY="你的真实 API Key"
    python extract_feedback.py

作为库使用：
    from extract_feedback import extract_customer_feedback
    result = extract_customer_feedback("客户反馈原文...")
    # result 是一个已经 json.loads 过的 dict，直接用即可
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import requests

try:
    import jsonschema
    from jsonschema import Draft7Validator

    _HAS_JSONSCHEMA = True
except ImportError:  # jsonschema 是可选依赖，缺失时退化为跳过本地二次校验
    _HAS_JSONSCHEMA = False

# 统一收敛需要触发“重试”的异常类型，避免在 except 子句里写条件表达式
_RETRYABLE_EXCEPTIONS: tuple = (
    requests.RequestException,
    json.JSONDecodeError,
    ValueError,
)
if _HAS_JSONSCHEMA:
    _RETRYABLE_EXCEPTIONS = _RETRYABLE_EXCEPTIONS + (jsonschema.ValidationError,)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("extract_feedback")


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 智谱开放平台（bigmodel.cn）Chat Completions 接口地址，OpenAI 兼容风格
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型名称：GLM-5.3（占位，按实际可用模型名替换）
ZHIPU_MODEL = "glm-5.3"

# API Key 从环境变量读取，不在代码里硬编码真实密钥
# 未设置时给一个明显的占位符，避免误用真实密钥场景下的空字符串请求
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "YOUR_ZHIPU_API_KEY_PLACEHOLDER")

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.5


# --------------------------------------------------------------------------
# JSON Schema 定义
# --------------------------------------------------------------------------
# 这份 Schema 同时用于两处：
#   1. 随请求发给智谱接口，驱动模型做结构化约束解码；
#   2. 收到响应后在本地用 jsonschema 再校验一遍，做兜底防护。
FEEDBACK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": ["string", "null"],
            "description": "客户姓名；反馈文本中未提及姓名时为 null",
        },
        "issue_type": {
            "type": "string",
            "description": "客户反馈的问题类型",
            "enum": [
                "product_quality",   # 产品质量问题
                "delivery",          # 物流/配送问题
                "billing",           # 账单/费用问题
                "account",           # 账号问题
                "service_attitude",  # 服务态度问题
                "feature_request",   # 功能建议
                "other",             # 其他
            ],
        },
        "urgency": {
            "type": "string",
            "description": "问题的紧急程度",
            "enum": ["low", "medium", "high", "critical"],
        },
    },
    "required": ["name", "issue_type", "urgency"],
    "additionalProperties": False,
}

# 提交给智谱接口的 json_schema 结构（OpenAI 兼容的 response_format 约定）
_RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "customer_feedback_extraction",
        "schema": FEEDBACK_SCHEMA,
        "strict": True,
    },
}

_SYSTEM_PROMPT = (
    "你是一个专业的客户反馈信息抽取助手。"
    "你会收到一段客户反馈原文，需要从中抽取以下三个字段："
    "1) name：客户姓名，文本中未出现姓名时填 null；"
    "2) issue_type：问题类型，只能从给定枚举中选择最贴切的一个；"
    "3) urgency：紧急程度，只能从给定枚举中选择，需结合文本中的情绪强度、"
    "是否影响资金/账号安全、是否有明确催促等因素综合判断。"
    "只输出严格符合给定 JSON Schema 的 JSON 对象本身，不要输出任何解释、"
    "前后缀文字或 Markdown 代码块标记。"
)


class FeedbackExtractionError(RuntimeError):
    """所有重试耗尽后仍未能拿到合法结构化结果时抛出。"""


def _build_payload(feedback_text: str) -> Dict[str, Any]:
    return {
        "model": ZHIPU_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": feedback_text},
        ],
        # 低温度，尽量减少枚举值以外的“创造性发挥”
        "temperature": 0.1,
        "response_format": _RESPONSE_FORMAT,
    }


def _call_zhipu_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """发起一次 HTTP 请求，返回解析后的响应 JSON（整个 chat completion 对象）。

    仅负责网络层面的请求/响应，不做业务字段校验。
    """
    headers = {
        "Authorization": f"Bearer {ZHIPU_API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        ZHIPU_API_URL,
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _extract_message_content(api_response: Dict[str, Any]) -> str:
    """从智谱 Chat Completions 响应中取出模型生成的文本内容。"""
    try:
        return api_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FeedbackExtractionError(
            f"接口返回结构不符合预期，无法定位 message.content: {api_response}"
        ) from exc


def _validate_against_schema(data: Dict[str, Any]) -> None:
    """本地二次校验，确保 data 严格符合 FEEDBACK_SCHEMA。

    这是防止「模型侧 strict 模式退化 / 网关不支持 json_schema」的最后一道保险。
    校验不通过时抛出 jsonschema.ValidationError，由上层统一捕获并触发重试。
    """
    if not _HAS_JSONSCHEMA:
        # 没装 jsonschema 库时，退化为最基本的手工检查，保证不完全裸奔
        required = FEEDBACK_SCHEMA["required"]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"缺少必需字段: {missing}")
        if data.get("issue_type") not in FEEDBACK_SCHEMA["properties"]["issue_type"]["enum"]:
            raise ValueError(f"issue_type 取值不在枚举内: {data.get('issue_type')!r}")
        if data.get("urgency") not in FEEDBACK_SCHEMA["properties"]["urgency"]["enum"]:
            raise ValueError(f"urgency 取值不在枚举内: {data.get('urgency')!r}")
        return

    validator = Draft7Validator(FEEDBACK_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        messages = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        raise jsonschema.ValidationError(f"本地 Schema 校验未通过: {messages}")


def extract_customer_feedback(
    feedback_text: str,
    max_retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    """从一段客户反馈文本中抽取结构化信息，保证返回值严格符合 FEEDBACK_SCHEMA。

    Args:
        feedback_text: 客户反馈原文。
        max_retries: 因“非法 JSON / 不符合 Schema / 网络错误”触发的最大重试次数。

    Returns:
        一个已经通过 json.loads 解析、并经过本地 Schema 校验的 dict，
        字段固定为 {"name", "issue_type", "urgency"}，可直接用于下游系统。

    Raises:
        FeedbackExtractionError: 重试耗尽后仍未拿到合法结构化结果。
    """
    if not feedback_text or not feedback_text.strip():
        raise ValueError("feedback_text 不能为空")

    payload = _build_payload(feedback_text)

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            api_response = _call_zhipu_api(payload)
            raw_content = _extract_message_content(api_response)

            # 兜底：即便开启了 json_schema 严格模式，也可能出现模型在内容外
            # 包了一层 Markdown 代码块（```json ... ```）的情况，先做一次
            # 轻量清洗，再交给 json.loads。
            cleaned_content = _strip_markdown_fence(raw_content)

            data = json.loads(cleaned_content)
            _validate_against_schema(data)

            logger.info("第 %d 次尝试成功，抽取结果: %s", attempt, data)
            return data

        except _RETRYABLE_EXCEPTIONS + (FeedbackExtractionError,) as exc:
            # 覆盖：网络/超时错误、JSON 解析失败、本地 Schema 校验失败（ValueError
            # 或 jsonschema.ValidationError，取决于是否安装了 jsonschema）、
            # 以及响应结构本身不符合预期（FeedbackExtractionError）。
            last_error = exc
            logger.warning(
                "第 %d/%d 次尝试失败: %s: %s",
                attempt,
                max_retries,
                type(exc).__name__,
                exc,
            )
            if attempt < max_retries:
                sleep_seconds = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)

    raise FeedbackExtractionError(
        f"重试 {max_retries} 次后仍未获得合法的结构化结果，最后一次错误: {last_error}"
    ) from last_error


def _strip_markdown_fence(text: str) -> str:
    """去除模型可能附带的 ```json ... ``` 包裹，返回纯 JSON 字符串。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # 去掉首行 ``` 或 ```json
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉末行 ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def main() -> None:
    sample_feedback = (
        "您好，我是王芳，昨天在你们平台下单的空气净化器到货后发现是坏的，"
        "开机就报警，我家里有小孩对空气质量要求很高，希望今天之内能给我处理，"
        "不然我就要申请平台介入了！"
    )

    if ZHIPU_API_KEY == "YOUR_ZHIPU_API_KEY_PLACEHOLDER":
        logger.warning(
            "检测到 ZHIPU_API_KEY 未设置，当前为占位符，实际运行前请先执行："
            "export ZHIPU_API_KEY=\"你的真实 API Key\""
        )

    try:
        result = extract_customer_feedback(sample_feedback)
    except FeedbackExtractionError as exc:
        logger.error("抽取失败: %s", exc)
        return

    # result 已经是 dict，这里为了演示“下游可以直接 json.loads 拿到同样的东西”，
    # 特意 dumps 一遍再 loads 一遍，实际业务里直接用 result 即可。
    result_json_text = json.dumps(result, ensure_ascii=False)
    parsed_by_downstream = json.loads(result_json_text)
    print(json.dumps(parsed_by_downstream, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
