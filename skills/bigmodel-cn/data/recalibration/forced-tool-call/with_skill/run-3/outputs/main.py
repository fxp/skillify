#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行客服机器人（智谱 GLM-5.3）。

用法:
    export ZHIPUAI_API_KEY=xxx
    python3 main.py "我的订单到哪了"

硬性业务要求: 无论用户问什么，回答之前一定先查一次订单。
实现方式说明（重要）:
    智谱开放平台的 `tool_choice` 目前只支持字符串 "auto"，传
    {"type":"function","function":{"name":"..."}} 这种强制指定单个函数的写法
    不会报错，但会被静默当成 auto 处理——模型完全可能对无关问题跳过工具调用。
    所以这里不依赖 tool_choice 来保证"必须调用"，而是在代码里**无条件先本地
    调用 lookup_order()**，再把查询结果作为上下文喂给模型；同时仍然把
    lookup_order 声明为 tool，允许模型在需要查另一个订单号时再次调用（走标准
    的 tool_calls -> role:"tool" 回传闭环）。
"""

import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
DEFAULT_ORDER_ID = "SO20260907001"
MAX_TOOL_ROUNDS = 3
REQUEST_TIMEOUT = 120


# --------------------------------------------------------------------------
# 本地工具实现（mock 数据）
# --------------------------------------------------------------------------
MOCK_ORDERS = {
    "SO20260907001": {
        "order_id": "SO20260907001",
        "status": "运输中",
        "goods": "人体工学椅 x1",
        "amount": 1299.00,
        "paid_at": "2026-09-03 10:12:35",
        "carrier": "顺丰速运",
        "tracking_no": "SF7712450039812",
        "latest_track": "2026-09-06 21:40 快件已到达【杭州转运中心】",
        "estimated_delivery": "2026-09-08",
        "address": "浙江省杭州市余杭区 **** （尾号 4821）",
    },
    "SO20260901077": {
        "order_id": "SO20260901077",
        "status": "已签收",
        "goods": "机械键盘 x1",
        "amount": 499.00,
        "paid_at": "2026-08-30 19:02:11",
        "carrier": "京东物流",
        "tracking_no": "JD9930127755",
        "latest_track": "2026-09-02 14:05 本人已签收",
        "estimated_delivery": "2026-09-02",
        "address": "浙江省杭州市余杭区 **** （尾号 4821）",
    },
}


def lookup_order(order_id: str) -> dict:
    """查询订单（mock）。每次被调用都会往 stderr 打一行日志。"""
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)
    order_id = (order_id or "").strip() or DEFAULT_ORDER_ID
    order = MOCK_ORDERS.get(order_id.upper())
    if order is None:
        return {
            "order_id": order_id,
            "found": False,
            "message": "未查询到该订单号对应的订单，请确认订单号是否正确。",
        }
    result = {"found": True}
    result.update(order)
    return result


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "查询订单的状态、物流轨迹、金额与预计送达时间。回答任何客服问题前都必须先查订单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 SO20260907001。用户未提供时使用其最近一笔订单号。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "你是一家电商平台的在线客服助手，语气礼貌、简洁、口语化，使用中文回答。"
    "系统已经替你查询过用户当前订单，订单数据会以工具结果的形式提供给你。"
    "无论用户问什么，你的回答都必须结合这份订单信息（例如主动同步物流进度或订单状态），"
    "不要编造订单数据中没有的信息。如果用户问的是另一个订单号，可以再次调用 lookup_order 工具查询。"
)


def extract_order_id(text: str) -> str:
    """从用户输入里尽量抽取订单号，抽不到就用默认（最近一笔）订单号。"""
    match = re.search(r"\b([A-Za-z]{2,4}\d{6,})\b", text)
    if match:
        return match.group(1).upper()
    match = re.search(r"\b(\d{8,})\b", text)
    if match:
        return match.group(1)
    return DEFAULT_ORDER_ID


def call_model(messages: list, api_key: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        # 注意: 智谱平台 tool_choice 仅支持 "auto"，强制指定函数无效（会被静默忽略），
        # "必须先查订单" 这个硬性要求靠下面代码里的无条件预调用来保证。
        "tool_choice": "auto",
        "stream": False,
    }
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        sys.exit(f"请求智谱 API 失败: {exc}")

    if resp.status_code != 200:
        sys.exit(f"智谱 API 返回 {resp.status_code}: {resp.text}")

    data = resp.json()
    if "error" in data:
        sys.exit(f"智谱 API 返回错误: {data['error']}")
    return data


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('用法: python3 main.py "我的订单到哪了"')
    user_message = " ".join(sys.argv[1:]).strip()

    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("未找到环境变量 ZHIPUAI_API_KEY，请先设置后再运行。")

    order_id = extract_order_id(user_message)

    # ---- 硬性要求：无条件先查一次订单，再让模型组织回答 ----
    order_info = lookup_order(order_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
        # 把预调用的结果以 assistant(tool_calls) + tool 的标准形式塞进上下文，
        # 模型看到的就是"订单已经查过了"，可以直接基于结果作答。
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_preflight_lookup_order",
                    "type": "function",
                    "function": {
                        "name": "lookup_order",
                        "arguments": json.dumps({"order_id": order_id}, ensure_ascii=False),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_preflight_lookup_order",
            "content": json.dumps(order_info, ensure_ascii=False),
        },
    ]

    # ---- 后续轮次：模型若还想查别的订单号，走标准 function calling 闭环 ----
    for _ in range(MAX_TOOL_ROUNDS):
        result = call_model(messages, api_key)
        message = result["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        # assistant 消息必须原样加回历史（含 tool_calls），顺序不能乱
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            }
            if tool_calls
            else {"role": "assistant", "content": message.get("content")}
        )

        if not tool_calls:
            # 判断是否为函数调用看 tool_calls / finish_reason，而不是 content 是否为空
            print((message.get("content") or "").strip())
            return

        for tool_call in tool_calls:
            if tool_call.get("type") == "function" and tool_call["function"]["name"] == "lookup_order":
                try:
                    args = json.loads(tool_call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result = lookup_order(str(args.get("order_id") or DEFAULT_ORDER_ID))
            else:
                tool_result = {"error": f"未知工具: {tool_call.get('function', {}).get('name')}"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    sys.exit("模型连续多轮请求工具调用，未能给出最终回答，请重试。")


if __name__ == "__main__":
    main()
