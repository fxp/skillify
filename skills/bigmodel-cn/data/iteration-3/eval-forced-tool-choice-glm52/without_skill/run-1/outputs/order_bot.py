#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
客服工单机器人 (order_bot.py)
================================

目标：不管用户说什么，模型在每一轮对话中都 *必须* 先调用
`lookup_order(order_id)` 工具查询订单状态，绝对不能让模型跳过
这一步、直接给出自由回答（哪怕用户问的是完全无关的问题）。

使用智谱 GLM（bigmodel.cn）的 HTTP Chat Completions 接口，
仅依赖标准库 + requests，不使用任何官方 SDK。

如何保证"工具必须被调用"（双重保险 / defense in depth）：

1. 【模型层强制】第一次请求时，通过 OpenAI 兼容的
   `tool_choice = {"type": "function", "function": {"name": "lookup_order"}}`
   参数，强制模型在本轮第一条回复中只能产出对 lookup_order 的调用，
   不允许它直接输出自然语言答案或调用别的函数。这是 bigmodel.cn
   v4 chat/completions 接口对 OpenAI tool_choice 协议的兼容实现。

2. 【代码层兜底】即使调用方（或模型、或未来的 API 版本）没有严格
   遵守 tool_choice、返回了不带 tool_calls 的纯文本回复，代码也绝不
   会把这段文本直接透传给用户。程序会检测 `finish_reason` /
   `tool_calls` 字段：如果没有看到 lookup_order 被调用，就在本地
   *强制* 合成一次 lookup_order 调用（自动从用户消息中提取订单号，
   提取不到则使用占位符），把工具结果重新注入对话历史，然后再进行
   第二轮请求。也就是说：无论模型"配不配合"，lookup_order 在返回
   给用户任何回答之前一定会被真实执行一次。

3. 只有在 lookup_order 的工具结果已经被写入对话历史之后，代码才会
   发起"允许自由回答"的第二次请求，让模型基于订单查询结果生成最终
   的自然语言答复。

注意：
- 这是一个可运行但离线可测试的脚本。真实调用需要在环境变量
  `ZHIPU_API_KEY` 中配置有效的智谱 API Key，否则请求会在
  `requests.post` 阶段收到鉴权失败的 HTTP 响应（这是预期行为，
  本脚本不包含真实、可用的 API Key）。
- `lookup_order` 本身是本地模拟实现（示例订单数据库），在真实项目
  中应替换为调用你自己的订单系统 / 数据库 / 内部 API。
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Optional

import requests

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 智谱开放平台 GLM 系列 Chat Completions 接口（OpenAI 兼容协议）。
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型名称：智谱 GLM-5.2。
MODEL_NAME = "glm-5.2"

# 从环境变量读取 API Key，占位符仅用于让脚本可以被直接运行/调试，
# 绝不要把真实 key 硬编码进代码。
API_KEY = os.environ.get("ZHIPU_API_KEY", "YOUR_ZHIPU_API_KEY_PLACEHOLDER")

REQUEST_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = (
    "你是一个客服工单机器人。你的唯一订单查询手段是 lookup_order 工具。"
    "在你回答用户的任何问题之前，你都必须先调用 lookup_order 查询当前"
    "工单/订单的状态，即使用户的问题看起来与订单无关，你也必须先完成"
    "这次查询，再结合查询结果或礼貌地说明情况来回答用户。"
    "禁止在没有调用 lookup_order 之前直接回答问题。"
)

# --------------------------------------------------------------------------
# 工具（function calling）定义
# --------------------------------------------------------------------------

LOOKUP_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": (
            "查询订单当前状态（如：待支付、待发货、已发货、已签收、已取消、"
            "退款中等）。任何一次对用户的回复之前都必须先调用本工具，"
            "即使暂时没有明确的订单号也要调用（此时传入能提取到的最佳猜测，"
            "或占位符 'UNKNOWN'）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号/工单号。如果用户没有提供，传 'UNKNOWN'。",
                }
            },
            "required": ["order_id"],
        },
    },
}

TOOLS = [LOOKUP_ORDER_TOOL]

# 强制模型在本轮第一条回复中只能调用 lookup_order，
# 不允许直接输出自然语言、也不允许调用其它函数。
FORCE_LOOKUP_ORDER_CHOICE = {
    "type": "function",
    "function": {"name": "lookup_order"},
}


# --------------------------------------------------------------------------
# 本地模拟的订单系统（真实项目中请替换为你自己的订单查询逻辑）
# --------------------------------------------------------------------------

_FAKE_ORDER_DB: dict[str, dict[str, Any]] = {
    "A10086": {"status": "已发货", "carrier": "顺丰速运", "eta": "2026-09-05"},
    "A10010": {"status": "待发货", "carrier": None, "eta": None},
    "A10001": {"status": "已签收", "carrier": "圆通速递", "eta": "2026-08-30"},
    "A10099": {"status": "退款中", "carrier": None, "eta": None},
}


def lookup_order(order_id: str) -> dict[str, Any]:
    """本地模拟的订单查询实现。

    真实场景下，这里应改为调用公司内部订单系统的 API / 数据库查询，
    而不是查一个内存字典。
    """
    order_id_normalized = (order_id or "").strip().upper()

    if not order_id_normalized or order_id_normalized == "UNKNOWN":
        return {
            "order_id": order_id_normalized or "UNKNOWN",
            "found": False,
            "status": "unknown",
            "message": "未能从用户输入中识别出有效订单号，请用户提供订单号后重新查询。",
        }

    record = _FAKE_ORDER_DB.get(order_id_normalized)
    if record is None:
        return {
            "order_id": order_id_normalized,
            "found": False,
            "status": "not_found",
            "message": "未查询到该订单号对应的订单，请核实订单号是否正确。",
        }

    return {
        "order_id": order_id_normalized,
        "found": True,
        **record,
    }


# --------------------------------------------------------------------------
# 从用户输入中尽力提取订单号（尽力而为，提取不到就用占位符）
# --------------------------------------------------------------------------

_ORDER_ID_PATTERNS = [
    # 例如 "订单号是A10086"、"订单号: A10086"、"工单号A10086"
    re.compile(r"(?:订单号|工单号|订单编号|单号)(?:是|为|[：:\s])*([A-Za-z0-9\-]{4,})"),
    # 兜底：直接在文本中找形如 "A10086" 的字母+数字组合。
    # 注意：不用 \b 做边界判断，因为 Python re 在 Unicode 模式下把中文
    # 字符也算作 \w，"是A10086" 这种紧邻中文字符的场景会导致 \b 匹配失败。
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,3}\d{5,})(?![A-Za-z0-9])"),
]


def extract_order_id(user_text: str) -> str:
    for pattern in _ORDER_ID_PATTERNS:
        match = pattern.search(user_text)
        if match:
            return match.group(1)
    return "UNKNOWN"


# --------------------------------------------------------------------------
# GLM HTTP 调用封装
# --------------------------------------------------------------------------

class GLMAPIError(RuntimeError):
    pass


def call_glm(
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]] = None,
    tool_choice: Any = None,
) -> dict[str, Any]:
    """调用智谱 GLM chat/completions 接口，返回解析后的 JSON。"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    response = requests.post(
        API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
    )

    if response.status_code != 200:
        raise GLMAPIError(
            f"GLM API 请求失败: HTTP {response.status_code} - {response.text}"
        )

    data = response.json()
    if "choices" not in data or not data["choices"]:
        raise GLMAPIError(f"GLM API 返回结果异常: {data}")

    return data


# --------------------------------------------------------------------------
# 核心逻辑：保证 lookup_order 一定先被调用
# --------------------------------------------------------------------------

def _extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    return message.get("tool_calls") or []


def _run_lookup_order_from_tool_call(tool_call: dict[str, Any], user_text: str) -> tuple[str, dict[str, Any]]:
    """执行某一个 tool_call（假定其 name 为 lookup_order），返回 (order_id, 结果)。"""
    raw_arguments = tool_call.get("function", {}).get("arguments") or "{}"
    try:
        args = json.loads(raw_arguments)
    except json.JSONDecodeError:
        args = {}

    order_id = args.get("order_id") or extract_order_id(user_text)
    result = lookup_order(order_id)
    return order_id, result


def ensure_lookup_order_called(
    messages: list[dict[str, Any]], user_text: str
) -> None:
    """第一次请求模型，并 *强制保证* lookup_order 在返回前被真实调用一次。

    副作用：把 assistant 的 tool_call 消息、以及 tool 的查询结果消息
    追加到 `messages` 中。
    """
    first_response = call_glm(
        messages,
        tools=TOOLS,
        tool_choice=FORCE_LOOKUP_ORDER_CHOICE,
    )
    assistant_message = first_response["choices"][0]["message"]
    tool_calls = _extract_tool_calls(assistant_message)

    lookup_order_calls = [
        tc for tc in tool_calls if tc.get("function", {}).get("name") == "lookup_order"
    ]

    if lookup_order_calls:
        # 正常路径：模型遵守了 tool_choice 强制约束，产出了 lookup_order 调用。
        messages.append(assistant_message)
        for tool_call in lookup_order_calls:
            order_id, result = _run_lookup_order_from_tool_call(tool_call, user_text)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        # 忽略/丢弃任何非 lookup_order 的额外调用（理论上 tool_choice 强制
        # 单一函数时不应出现，这里再加一层保险，不把它们写回历史）。
        return

    # 兜底路径：模型（或未来的 API 行为变化）没有按预期返回 tool_calls，
    # 也就是说没有直接的证据证明 lookup_order 被调用了。
    # 绝不能把 assistant_message 里可能存在的自由文本直接透传给用户，
    # 我们在本地强制合成一次 lookup_order 调用并执行它。
    forced_call_id = "forced_lookup_order_call"
    forced_order_id = extract_order_id(user_text)
    forced_result = lookup_order(forced_order_id)

    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": forced_call_id,
                    "type": "function",
                    "function": {
                        "name": "lookup_order",
                        "arguments": json.dumps({"order_id": forced_order_id}),
                    },
                }
            ],
        }
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": forced_call_id,
            "content": json.dumps(forced_result, ensure_ascii=False),
        }
    )


def get_final_reply(messages: list[dict[str, Any]]) -> str:
    """在 lookup_order 结果已经写入历史之后，允许模型自由生成最终回复。"""
    final_response = call_glm(messages, tools=TOOLS, tool_choice="auto")
    final_message = final_response["choices"][0]["message"]
    messages.append(final_message)
    return final_message.get("content") or ""


def handle_user_turn(messages: list[dict[str, Any]], user_text: str) -> str:
    """处理一轮用户输入：先强制查询订单，再生成回复。"""
    messages.append({"role": "user", "content": user_text})

    # 第一步（强制）：lookup_order 必须先被调用一次，函数内部有双重保险。
    ensure_lookup_order_called(messages, user_text)

    # 第二步：基于订单查询结果，让模型生成面向用户的自然语言回复。
    return get_final_reply(messages)


# --------------------------------------------------------------------------
# 简单的命令行交互入口
# --------------------------------------------------------------------------

def new_conversation() -> list[dict[str, Any]]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def main() -> None:
    print("客服工单机器人已启动（输入 exit / quit 退出）。")
    print(f"当前使用模型: {MODEL_NAME}")
    if API_KEY == "YOUR_ZHIPU_API_KEY_PLACEHOLDER":
        print(
            "警告: 未检测到有效的 ZHIPU_API_KEY 环境变量，"
            "当前使用占位符，真实请求会返回鉴权失败。",
            file=sys.stderr,
        )

    messages = new_conversation()

    while True:
        try:
            user_text = input("用户: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            print("再见。")
            break

        try:
            reply = handle_user_turn(messages, user_text)
        except GLMAPIError as exc:
            print(f"[系统] 调用 GLM API 出错: {exc}", file=sys.stderr)
            continue
        except requests.RequestException as exc:
            print(f"[系统] 网络请求出错: {exc}", file=sys.stderr)
            continue

        print(f"客服机器人: {reply}")


if __name__ == "__main__":
    main()
