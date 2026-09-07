#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行客服机器人（智谱 GLM）。

用法:
    export ZHIPUAI_API_KEY=xxx
    python3 main.py "我的订单到哪了"

硬性业务要求: 无论用户问什么, 在生成最终回答之前必须先调用一次
lookup_order(order_id) 工具。实现上通过 tool_choice 强制模型首轮调用该函数,
若模型仍未调用, 脚本会在本地兜底调用一次并把结果回灌给模型, 保证"回答前
一定查过订单"。
"""

import json
import os
import sys
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
DEFAULT_ORDER_ID = "SO20260907001"
MAX_ROUNDS = 5
TIMEOUT = 120


# --------------------------------------------------------------------------
# 本地工具实现
# --------------------------------------------------------------------------
MOCK_ORDERS = {
    "SO20260907001": {
        "order_id": "SO20260907001",
        "status": "运输中",
        "goods": "人体工学椅 X1 · 深灰",
        "amount": 1299.00,
        "paid_at": "2026-09-03 10:24:11",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890123",
        "latest_track": "2026-09-06 21:10 快件已到达【杭州转运中心】",
        "eta": "2026-09-08",
        "receiver": "张先生 / 138****6677 / 浙江省杭州市余杭区",
    }
}


def lookup_order(order_id):
    """查询订单（mock 数据）。每次被调用都会向 stderr 打印一行标记。"""
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)

    oid = (order_id or "").strip() or DEFAULT_ORDER_ID
    order = MOCK_ORDERS.get(oid)
    if order is None:
        # 未命中时返回默认订单，避免因为用户没给单号就查不到
        order = dict(MOCK_ORDERS[DEFAULT_ORDER_ID])
        order["note"] = "未找到 %s，已返回该用户最近一笔订单" % oid
    return order


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "查询用户订单的当前状态、物流轨迹、金额与收货信息。"
                "任何客服问题在回答前都必须先调用本工具查一次订单。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号；用户没有提供时传空字符串，系统会取其最近一笔订单。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "你是一名电商客服助手。硬性规则：无论用户问什么（哪怕是闲聊或与订单无关的问题），"
    "你都必须先调用 lookup_order 工具查询一次订单，拿到订单信息之后才能组织最终回答。"
    "回答要简洁、口语化、中文，并结合查到的订单真实信息作答；不要编造工具没有返回的内容。"
)


# --------------------------------------------------------------------------
# API 调用
# --------------------------------------------------------------------------
def call_api(api_key, messages, tool_choice):
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": tool_choice,
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "API 调用失败 HTTP %s: %s" % (resp.status_code, resp.text[:1000])
        )
    return resp.json()


def run_tool_calls(assistant_msg, messages):
    """执行 assistant 返回的所有 tool_calls，并把结果追加进 messages。"""
    for call in assistant_msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        name = fn.get("name")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (ValueError, TypeError):
            args = {}

        if name == "lookup_order":
            result = lookup_order(args.get("order_id", ""))
        else:
            result = {"error": "unknown tool: %s" % name}

        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            }
        )


def inject_forced_lookup(messages):
    """模型没按要求调用工具时的兜底：本地强制查一次并回灌结果。"""
    call_id = "call_" + uuid.uuid4().hex[:16]
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "lookup_order",
                        "arguments": json.dumps(
                            {"order_id": DEFAULT_ORDER_ID}, ensure_ascii=False
                        ),
                    },
                }
            ],
        }
    )
    result = lookup_order(DEFAULT_ORDER_ID)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result, ensure_ascii=False),
        }
    )


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python3 main.py "我的订单到哪了"', file=sys.stderr)
        return 2

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 2

    user_message = " ".join(a for a in sys.argv[1:]).strip()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # 首轮强制调用 lookup_order；之后交给模型自行决定。
    tool_choice = {"type": "function", "function": {"name": "lookup_order"}}
    tool_was_called = False

    try:
        for _ in range(MAX_ROUNDS):
            try:
                data = call_api(api_key, messages, tool_choice)
            except RuntimeError:
                # 个别情况下强制 tool_choice 不被接受，退回 auto 再试一次
                if tool_choice != "auto":
                    tool_choice = "auto"
                    data = call_api(api_key, messages, tool_choice)
                else:
                    raise

            choice = (data.get("choices") or [{}])[0]
            assistant_msg = choice.get("message") or {}
            messages.append(assistant_msg)

            if assistant_msg.get("tool_calls"):
                run_tool_calls(assistant_msg, messages)
                tool_was_called = True
                tool_choice = "auto"  # 后续轮次不再强制
                continue

            if not tool_was_called:
                # 模型没调工具就想直接回答 —— 兜底强制查一次订单再让它重答
                messages.pop()  # 丢掉这条未依据订单信息的回答
                inject_forced_lookup(messages)
                tool_was_called = True
                tool_choice = "auto"
                continue

            content = assistant_msg.get("content") or ""
            print(content.strip())
            return 0

        print("错误: 超过最大工具调用轮次仍未得到最终回答", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print("错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
