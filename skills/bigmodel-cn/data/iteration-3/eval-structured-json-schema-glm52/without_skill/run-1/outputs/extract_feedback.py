#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_feedback.py

从一段客户反馈文本中，用智谱 GLM-5.2 抽取结构化信息：
    - name        客户姓名
    - issue_type  问题类型
    - urgency     紧急程度

设计目标：调用方拿到返回值后可以直接 json.loads()，不需要自己写正则 /
try-except 一大堆容错解析逻辑。为此做了两层保证：

  1. 请求层：使用智谱 GLM-5.2 的 `response_format = {"type": "json_schema", ...}`
     （OpenAI 兼容的“结构化输出”模式），把我们定义的 JSON Schema 直接下发给
     模型，让模型在解码阶段就被强制约束成合法 JSON，而不是靠 prompt 里
     “请返回 JSON” 这种软约束。

  2. 应用层：即便如此，仍然对模型返回内容做「解析 -> Schema 校验」，一旦
     失败就自动重试（最多 MAX_RETRIES 次，指数退避），重试时把上一次的
     错误信息也带回给模型，帮助它自我纠正。全部重试失败后抛出
     StructuredExtractionError，绝不会把一个不合法的字符串静默返回给
     调用方——调用方要么拿到保证合法的 dict，要么拿到明确的异常。

仅依赖 Python 标准库 + requests。

用法：
    export ZHIPUAI_API_KEY="你的智谱 API Key（占位符）"
    python extract_feedback.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 智谱开放平台 (bigmodel.cn) 的 Chat Completions 接口，OpenAI 兼容格式。
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型名称。GLM-5.2 是占位模型名，如后续版本号变化，改这里即可，
# 也允许通过环境变量覆盖，方便切换/测试。
MODEL_NAME = os.environ.get("ZHIPUAI_MODEL", "glm-5.2")

# API Key 从环境变量读取，绝不要硬编码在代码里。
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.5


# --------------------------------------------------------------------------
# 输出的 JSON Schema
#
# 用受控枚举而不是自由文本描述 issue_type / urgency，这样后续系统可以直接
# 用等值比较分支处理，不用再猜测模型可能写出的各种同义表达。
# --------------------------------------------------------------------------

FEEDBACK_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "客户姓名；若原文没有明确提及，返回空字符串 \"\"。",
        },
        "issue_type": {
            "type": "string",
            "description": "客户反馈所属的问题类型。",
            "enum": [
                "billing",       # 账单/费用问题
                "technical",     # 技术故障/使用问题
                "shipping",      # 物流/配送问题
                "quality",       # 产品质量问题
                "service",       # 服务态度/客服问题
                "refund",        # 退款/退货
                "other",         # 其他，无法归类
            ],
        },
        "urgency": {
            "type": "string",
            "description": "问题的紧急程度。",
            "enum": ["low", "medium", "high", "urgent"],
        },
    },
    "required": ["name", "issue_type", "urgency"],
    "additionalProperties": False,
}

# 提交给智谱接口的 response_format 结构（OpenAI 结构化输出风格）。
RESPONSE_FORMAT: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "customer_feedback_extraction",
        "schema": FEEDBACK_JSON_SCHEMA,
        "strict": True,
    },
}

SYSTEM_PROMPT = (
    "你是一个只输出 JSON 的信息抽取助手。"
    "根据用户提供的客户反馈文本，抽取以下字段：\n"
    "- name: 客户姓名，原文若未提及则填空字符串\n"
    "- issue_type: 从 [billing, technical, shipping, quality, service, refund, other] 中选择最贴切的一个\n"
    "- urgency: 从 [low, medium, high, urgent] 中选择最贴切的一个，"
    "结合语气、措辞（如“立刻”“马上”“投诉”等）和影响范围综合判断\n"
    "只返回严格符合给定 JSON Schema 的 JSON 对象，不要输出任何解释、前后缀、Markdown 代码块标记。"
)


class StructuredExtractionError(RuntimeError):
    """当模型在多次重试后仍未能返回合法且符合 Schema 的 JSON 时抛出。"""


# --------------------------------------------------------------------------
# Schema 校验（不引入 jsonschema 第三方依赖，手写一个够用的最小校验器，
# 专门针对上面这个固定 Schema。如果环境里恰好装了 jsonschema，会优先用它，
# 校验更严谨；没装也不影响脚本运行。）
# --------------------------------------------------------------------------

def _validate_with_jsonschema_lib(data: Dict[str, Any]) -> Optional[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return None  # 表示"库不可用，调用方应改用手写校验"

    try:
        jsonschema.validate(instance=data, schema=FEEDBACK_JSON_SCHEMA)
    except jsonschema.exceptions.ValidationError as exc:  # type: ignore
        return str(exc.message)
    return ""  # 空字符串表示校验通过


def _validate_manually(data: Dict[str, Any]) -> str:
    """返回空字符串表示通过，否则返回错误描述。"""
    if not isinstance(data, dict):
        return f"顶层结果不是 JSON object，而是 {type(data).__name__}"

    required = FEEDBACK_JSON_SCHEMA["required"]
    for key in required:
        if key not in data:
            return f"缺少必填字段: {key}"

    allowed_keys = set(FEEDBACK_JSON_SCHEMA["properties"].keys())
    extra_keys = set(data.keys()) - allowed_keys
    if extra_keys:
        return f"包含未定义字段: {sorted(extra_keys)}"

    if not isinstance(data.get("name"), str):
        return "name 字段必须是字符串"

    if data.get("issue_type") not in FEEDBACK_JSON_SCHEMA["properties"]["issue_type"]["enum"]:
        return (
            "issue_type 取值不在允许范围内: "
            f"{data.get('issue_type')!r}"
        )

    if data.get("urgency") not in FEEDBACK_JSON_SCHEMA["properties"]["urgency"]["enum"]:
        return f"urgency 取值不在允许范围内: {data.get('urgency')!r}"

    return ""


def validate_against_schema(data: Dict[str, Any]) -> str:
    """校验 data 是否符合 FEEDBACK_JSON_SCHEMA。返回空字符串表示通过，
    否则返回可读的错误信息（用于重试时反馈给模型）。"""
    lib_result = _validate_with_jsonschema_lib(data)
    if lib_result is not None:
        return lib_result
    return _validate_manually(data)


# --------------------------------------------------------------------------
# 核心调用逻辑
# --------------------------------------------------------------------------

def _get_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise EnvironmentError(
            f"未找到环境变量 {API_KEY_ENV_VAR}，请先执行："
            f'\n    export {API_KEY_ENV_VAR}="your-zhipu-api-key"'
        )
    return api_key


def _build_messages(
    feedback_text: str, prior_error: Optional[str] = None
) -> List[Dict[str, str]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"客户反馈原文：\n{feedback_text}"},
    ]
    if prior_error:
        # 重试时把上一轮的失败原因带回去，帮助模型自我纠正。
        messages.append(
            {
                "role": "user",
                "content": (
                    "你上一次的输出未通过校验，原因是："
                    f"{prior_error}\n"
                    "请重新输出一个严格符合 Schema 的 JSON 对象。"
                ),
            }
        )
    return messages


def _call_api_once(
    feedback_text: str,
    api_key: str,
    prior_error: Optional[str] = None,
) -> str:
    """发起一次 HTTP 请求，返回模型输出的原始文本（未解析）。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": _build_messages(feedback_text, prior_error),
        "temperature": 0,  # 结构化抽取任务，追求稳定可复现，不需要创造性
        "response_format": RESPONSE_FORMAT,
    }

    resp = requests.post(
        API_URL,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    body = resp.json()

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise StructuredExtractionError(
            f"接口返回结构异常，无法找到 choices[0].message.content: {body!r}"
        ) from exc

    return content


def extract_feedback(feedback_text: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    对一段客户反馈文本做结构化抽取，返回严格符合 FEEDBACK_JSON_SCHEMA 的 dict。

    调用方可以放心地对返回值做 data["name"] / data["issue_type"] /
    data["urgency"]，不需要额外判空或做容错解析——一旦这里返回，说明
    已经通过了 Schema 校验；否则会抛出 StructuredExtractionError。
    """
    if not feedback_text or not feedback_text.strip():
        raise ValueError("feedback_text 不能为空")

    resolved_api_key = api_key or _get_api_key()

    last_error = None
    prior_error_for_retry: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_content = _call_api_once(
                feedback_text, resolved_api_key, prior_error_for_retry
            )
        except requests.exceptions.RequestException as exc:
            last_error = f"HTTP 请求失败: {exc}"
        else:
            # 即使开启了 strict json_schema 模式，也不完全信任网络对端，
            # 这里仍然做一次 json.loads + schema 校验兜底。
            try:
                data = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                last_error = f"返回内容不是合法 JSON: {exc}; 原始内容: {raw_content!r}"
            else:
                validation_error = validate_against_schema(data)
                if not validation_error:
                    return data  # 成功：合法 JSON 且符合 Schema
                last_error = f"JSON 合法但不符合 Schema: {validation_error}"

        prior_error_for_retry = last_error
        if attempt < MAX_RETRIES:
            sleep_seconds = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            time.sleep(sleep_seconds)

    raise StructuredExtractionError(
        f"重试 {MAX_RETRIES} 次后仍未获得合法且符合 Schema 的结果。最后一次错误: {last_error}"
    )


# --------------------------------------------------------------------------
# 命令行入口 / 示例
# --------------------------------------------------------------------------

def main() -> int:
    sample_feedback = (
        "您好，我是张伟，昨天在你们平台买的空气净化器到货后发现开机就报警，"
        "联系了在线客服半天没人理我，这机器我们家老人急用，"
        "麻烦今天之内给我解决方案，不然我就申请退款投诉了！"
    )

    try:
        result = extract_feedback(sample_feedback)
    except EnvironmentError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 1
    except StructuredExtractionError as exc:
        print(f"[抽取失败] {exc}", file=sys.stderr)
        return 2

    # 到这里 result 已保证是合法 JSON（dict），下游系统可以直接用。
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
