#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行客服机器人（智谱 GLM-5.3）

用法：
    export ZHIPUAI_API_KEY=xxx
    python3 main.py "我的订单到哪了"

硬性业务要求：无论用户问什么，回答之前一定先调用一次本地工具函数
lookup_order(order_id) 查订单，拿到结果后再由模型组织最终回答。

注意：智谱开放平台的 tool_choice 目前「默认且仅支持 auto」，不支持
{"type": "function", ...} 或 "required" 这类强制指定。所以这里不能靠
tool_choice 来保证工具一定被调用，而是由脚本自己兜底：
  1. 第一轮带 tools 让模型自己发起 lookup_order 调用；
  2. 如果模型没调（直接回话了），脚本丢弃这次回复，主动本地调用一次
     lookup_order，把结果以标准 tool 消息注入上下文；
  3. 第二轮再让模型基于订单数据组织最终回答。
这样在任何路径下 lookup_order 都恰好被调用一次，且一定发生在最终回答之前。
"""

import json
import os
import re
import sys
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
TIMEOUT = 300

SYSTEM_PROMPT = (
    "你是一家电商平台的中文在线客服。"
    "业务硬性规定：在回答用户的任何问题之前，你必须先调用 lookup_order 工具查询一次订单，"
    "不允许在没有订单查询结果的情况下作答。"
    "如果用户没有提供订单号，就用默认订单号 DEFAULT 调用该工具。"
    "拿到订单数据后，结合订单的真实状态用简洁、友好的中文回答用户，"
    "并自然地把订单号、状态、物流信息等关键事实说清楚。"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "查询订单的当前状态与物流信息。回答用户任何问题之前都必须先调用一次。"
                "用户没给订单号时传 DEFAULT。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 20260907001；未知时传 DEFAULT",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]


# --------------------------------------------------------------------------
# 本地工具实现（mock 数据）
# --------------------------------------------------------------------------
def lookup_order(order_id: str) -> dict:
    """查订单，返回 mock 数据。每次被调用都会往 stderr 打一行标记。"""
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)

    order_id = (order_id or "DEFAULT").strip() or "DEFAULT"
    if order_id.upper() == "DEFAULT":
        order_id = "20260901-88213"

    return {
        "order_id": order_id,
        "status": "in_transit",
        "status_text": "运输中",
        "items": [{"name": "无线降噪耳机 Pro", "quantity": 1, "price": 899.00}],
        "total_amount": 899.00,
        "currency": "CNY",
        "paid_at": "2026-09-01 21:14:33",
        "shipped_at": "2026-09-02 10:05:12",
        "carrier": "顺丰速运",
        "tracking_number": "SF1234567890123",
        "latest_trace": "2026-09-06 18:40 快件已到达【杭州转运中心】",
        "estimated_delivery": "2026-09-08",
        "receiver": {"name": "冯**", "city": "杭州市", "phone": "138****5678"},
        "refundable": True,
    }


TOOL_IMPLS = {"lookup_order": lookup_order}


def guess_order_id(text: str) -> str:
    """从用户消息里粗略猜一个订单号，猜不到就用 DEFAULT。"""
    m = re.search(r"\b[0-9]{6,}(?:-[0-9]{3,})?\b", text or "")
    return m.group(0) if m else "DEFAULT"


# --------------------------------------------------------------------------
# 模型调用
# --------------------------------------------------------------------------
def chat(api_key: str, messages: list, with_tools: bool) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        # GLM-5.3 始终开启思考，只能是 enabled；reasoning_effort 可选 low/high/max
        "thinking": {"type": "enabled"},
        "reasoning_effort": "low",
        "temperature": 0.6,
        "max_tokens": 4096,
    }
    if with_tools:
        payload["tools"] = TOOLS
        # 智谱目前只支持 auto，写死别的值会报错
        payload["tool_choice"] = "auto"

    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"接口返回 HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    if "choices" not in data:
        raise RuntimeError(f"接口返回异常: {json.dumps(data, ensure_ascii=False)[:500]}")
    return data["choices"][0]["message"]


def run_tool_call(call: dict) -> dict:
    """执行一个 tool_call，返回要回传给模型的 tool 消息。"""
    fn = call.get("function", {}) or {}
    name = fn.get("name", "")
    raw_args = fn.get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (ValueError, TypeError):
        args = {}

    impl = TOOL_IMPLS.get(name)
    if impl is None:
        result = {"error": f"未知工具: {name}"}
    else:
        result = impl(args.get("order_id", "DEFAULT"))

    return {
        "role": "tool",
        "tool_call_id": call.get("id", ""),
        "content": json.dumps(result, ensure_ascii=False),
    }


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python3 main.py "我的订单到哪了"', file=sys.stderr)
        return 2
    user_message = " ".join(sys.argv[1:]).strip()

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 2

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # 第一轮：带工具，让模型自己发起 lookup_order 调用
    try:
        first = chat(api_key, messages, with_tools=True)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"调用模型失败: {exc}", file=sys.stderr)
        return 1

    tool_calls = first.get("tool_calls") or []
    lookup_calls = [
        c for c in tool_calls if (c.get("function") or {}).get("name") == "lookup_order"
    ]

    if lookup_calls:
        messages.append(
            {
                "role": "assistant",
                "content": first.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            messages.append(run_tool_call(call))
    else:
        # 兜底：模型没听话（或直接给了答案），脚本强制查一次订单再让它重答
        call_id = "call_" + uuid.uuid4().hex[:16]
        forced_call = {
            "id": call_id,
            "type": "function",
            "function": {
                "name": "lookup_order",
                "arguments": json.dumps(
                    {"order_id": guess_order_id(user_message)}, ensure_ascii=False
                ),
            },
        }
        messages.append({"role": "assistant", "content": "", "tool_calls": [forced_call]})
        messages.append(run_tool_call(forced_call))

    messages.append(
        {
            "role": "system",
            "content": "订单查询结果已在上方 tool 消息中给出，请据此直接回答用户，不要再调用工具。",
        }
    )

    # 第二轮：基于订单数据组织最终回答
    try:
        final = chat(api_key, messages, with_tools=False)
    except (requests.RequestException, RuntimeError) as exc:
        print(f"调用模型失败: {exc}", file=sys.stderr)
        return 1

    answer = (final.get("content") or "").strip()
    if not answer:
        print("模型没有返回可用的回答内容。", file=sys.stderr)
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
