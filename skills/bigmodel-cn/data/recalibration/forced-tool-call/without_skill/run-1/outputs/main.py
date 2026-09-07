#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行客服机器人（智谱 GLM-5.3）

用法:
    export ZHIPUAI_API_KEY=xxxx
    python3 main.py "我的订单到哪了"

硬性业务要求:
    无论用户问什么，在生成最终回答之前，必须先调用一次本地工具函数
    lookup_order(order_id) 查询订单，拿到结果后再组织最终回答。
    lookup_order 每次被调用都会往 stderr 打印 [TOOL] lookup_order called。

依赖: 仅 requests。
"""

import json
import os
import re
import sys
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
REQUEST_TIMEOUT = 300
MAX_ROUNDS = 6  # 防止工具调用死循环

SYSTEM_PROMPT = (
    "你是一名电商平台的中文在线客服助手。\n"
    "【强制流程】无论用户问什么问题（哪怕是闲聊、问天气、问退货政策），"
    "你都必须先调用 lookup_order 工具查询一次订单，拿到订单查询结果之后，"
    "才能组织并给出最终回答。不允许在没有调用 lookup_order 的情况下直接回答。\n"
    "如果用户没有提供订单号，就用你能推断出的订单号调用；"
    "实在没有线索时，使用订单号 \"UNKNOWN\" 调用。\n"
    "最终回答请使用简体中文，语气友好、简洁，并结合工具返回的订单信息作答。"
)

# ---------------------------------------------------------------- 本地工具实现


def lookup_order(order_id):
    """查询订单（mock 实现）。每次被调用都会在 stderr 留下痕迹。"""
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)

    order_id = (order_id or "UNKNOWN").strip() or "UNKNOWN"
    return {
        "order_id": order_id,
        "status": "运输中",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890123",
        "items": [
            {"name": "无线蓝牙耳机 Pro", "quantity": 1, "price": 499.00},
            {"name": "Type-C 快充线 1.5m", "quantity": 2, "price": 29.00},
        ],
        "total_amount": 557.00,
        "currency": "CNY",
        "paid_at": "2026-09-03 14:22:11",
        "shipped_at": "2026-09-04 09:05:40",
        "current_location": "杭州转运中心",
        "estimated_delivery": "2026-09-08",
        "receiver": {"name": "冯先生", "city": "杭州市", "phone": "138****6621"},
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "查询订单的物流与详情信息。回答用户任何问题之前都必须先调用一次。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号；用户未提供时传 \"UNKNOWN\"。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

TOOL_IMPLS = {"lookup_order": lookup_order}


def guess_order_id(text):
    """从用户消息里粗略猜一个订单号，猜不到就返回 UNKNOWN。"""
    m = re.search(r"\b([A-Za-z]{0,4}[-_]?\d{6,})\b", text or "")
    return m.group(1) if m else "UNKNOWN"


# ---------------------------------------------------------------- API 调用


def call_api(api_key, messages):
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",  # 智谱 API 目前仅支持 auto
            "temperature": 0.6,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "智谱 API 调用失败 HTTP {}: {}".format(resp.status_code, resp.text[:1000])
        )
    return resp.json()


def run_tool_calls(tool_calls):
    """执行模型请求的工具调用，返回 role=tool 的消息列表。"""
    tool_messages = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name")
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (ValueError, TypeError):
            args = {}

        impl = TOOL_IMPLS.get(name)
        if impl is None:
            result = {"error": "未知工具: {}".format(name)}
        else:
            result = impl(**args) if args else impl("UNKNOWN")

        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    return tool_messages


def force_lookup_order(user_message):
    """
    兜底：模型没主动调工具时，由本地代码强制调用一次 lookup_order，
    并伪造一轮 assistant tool_call + tool 结果注入上下文，
    确保"回答之前一定查过订单"这条硬性业务要求成立。
    """
    order_id = guess_order_id(user_message)
    call_id = "call_" + uuid.uuid4().hex[:16]
    result = lookup_order(order_id)

    assistant_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "lookup_order",
                    "arguments": json.dumps({"order_id": order_id}, ensure_ascii=False),
                },
            }
        ],
    }
    tool_msg = {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }
    return [assistant_msg, tool_msg]


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python3 main.py "我的订单到哪了"', file=sys.stderr)
        return 2

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 2

    user_message = " ".join(sys.argv[1:]).strip()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    tool_was_called = False

    for _ in range(MAX_ROUNDS):
        data = call_api(api_key, messages)
        choices = data.get("choices") or []
        if not choices:
            print("错误: 智谱 API 返回了空的 choices: {}".format(data), file=sys.stderr)
            return 1

        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []

        if tool_calls:
            # 回填 assistant 的工具调用消息（丢弃 reasoning_content 等非必要字段）
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            messages.extend(run_tool_calls(tool_calls))
            tool_was_called = True
            continue

        # 模型想直接作答
        if not tool_was_called:
            # 硬性要求未满足 —— 本地强制查一次订单，再让模型重新组织回答
            messages.extend(force_lookup_order(user_message))
            tool_was_called = True
            continue

        content = (message.get("content") or "").strip()
        if not content:
            print("错误: 模型返回了空回答。", file=sys.stderr)
            return 1
        print(content)
        return 0

    print("错误: 工具调用轮次超过上限，未能得到最终回答。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.RequestException as exc:
        print("网络请求异常: {}".format(exc), file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
