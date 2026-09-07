#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行客服机器人（智谱 GLM-5.3）。

用法:
    export ZHIPUAI_API_KEY=xxx
    python3 main.py "我的订单到哪了"

硬性业务要求：无论用户问什么，回答前一定要先调用 lookup_order() 查一次订单。
实现说明（重要）：智谱开放平台的 `tool_choice` 目前只支持字符串 "auto"，
传 {"type":"function","function":{"name":"..."}} 不会报错但会被当成 auto 静默处理，
模型完全可能对无关问题跳过工具调用。所以这里不依赖 tool_choice 做强制，
而是在代码里**无条件先执行** lookup_order()，把结果作为上下文喂给模型；
同时仍然把该函数注册进 tools，允许模型在需要查别的订单号时再次调用。
"""

import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
DEFAULT_ORDER_ID = "SO20260907001"
TIMEOUT = 120


# --------------------------------------------------------------------------
# 本地工具函数（mock 数据）
# --------------------------------------------------------------------------
def lookup_order(order_id: str) -> dict:
    """查询订单，返回 mock 数据。每次被调用都会往 stderr 打一行标记。"""
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)
    return {
        "order_id": order_id,
        "status": "运输中",
        "items": [{"name": "无线降噪耳机 Pro", "quantity": 1, "price": 899.00}],
        "total_amount": 899.00,
        "paid_at": "2026-09-03 14:22:10",
        "shipped_at": "2026-09-04 09:15:00",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890123",
        "current_location": "杭州转运中心",
        "estimated_delivery": "2026-09-08",
        "receiver": {"name": "张*", "phone": "138****6677", "city": "杭州市"},
        "refundable": True,
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "根据订单号查询订单的状态、物流、金额等详细信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 SO20260907001",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "你是一名电商平台的在线客服。回答要简洁、礼貌、口语化，用中文回复。"
    "系统已经为你预先查询了当前用户的订单信息，请**必须**结合这份订单数据来回答，"
    "不要编造订单号、物流状态或时间。如果用户的问题和订单无关，也要先简单确认订单状态再回答问题。"
    "如果需要查询其它订单号，可以调用 lookup_order 工具。"
)


def extract_order_id(text: str) -> str:
    """从用户消息里尽量提取订单号；提取不到就用当前会话的默认订单。"""
    match = re.search(r"\b([A-Za-z]{2,4}\d{6,})\b", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{8,})\b", text)
    if match:
        return match.group(1)
    return DEFAULT_ORDER_ID


def call_model(messages: list, api_key: str) -> dict:
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
            "tool_choice": "auto",
            # glm-5.3 在标准端点强制思考，无法用 thinking.disabled 关闭（会报 1210），
            # 只能用 reasoning_effort 调节强度；客服问答用 low 即可。
            "reasoning_effort": "low",
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "调用智谱 API 失败 (HTTP %s): %s" % (resp.status_code, resp.text)
        )
    return resp.json()


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python3 main.py "我的订单到哪了"', file=sys.stderr)
        return 2

    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 2

    user_message = " ".join(sys.argv[1:]).strip()

    # === 硬性要求：回答之前无条件先查一次订单 ===
    order_id = extract_order_id(user_message)
    order_info = lookup_order(order_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "已查询到的当前用户订单信息（JSON）：\n"
            + json.dumps(order_info, ensure_ascii=False, indent=2),
        },
        {"role": "user", "content": user_message},
    ]

    try:
        result = call_model(messages, api_key)
        message = result["choices"][0]["message"]

        # 模型可能还想查别的订单号，最多再跑 3 轮工具调用。
        for _ in range(3):
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                break
            # assistant 消息（含 tool_calls 与 reasoning_content）必须原样加回历史
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "reasoning_content": message.get("reasoning_content"),
                    "tool_calls": tool_calls,
                }
            )
            for tool_call in tool_calls:
                if tool_call.get("type") != "function":
                    continue
                fn = tool_call["function"]
                if fn["name"] != "lookup_order":
                    tool_result = {"error": "unknown tool: " + fn["name"]}
                else:
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_result = lookup_order(
                        str(args.get("order_id") or order_id)
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
            result = call_model(messages, api_key)
            message = result["choices"][0]["message"]

        answer = (message.get("content") or "").strip()
        if not answer:
            print("模型未返回有效回答。", file=sys.stderr)
            return 1
        print(answer)
        return 0
    except requests.RequestException as exc:
        print("网络请求异常：%s" % exc, file=sys.stderr)
        return 1
    except (RuntimeError, KeyError, ValueError) as exc:
        print("处理失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
