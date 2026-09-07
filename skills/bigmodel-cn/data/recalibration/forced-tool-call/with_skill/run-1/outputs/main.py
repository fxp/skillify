#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行客服机器人（智谱 GLM-5.3）。

用法:
    export ZHIPUAI_API_KEY=...
    python3 main.py "我的订单到哪了"

硬性业务要求：无论用户问什么，回答前**一定**先调用一次 lookup_order()。
实现方式说明（重要）：
    智谱标准端点的 `tool_choice` 只支持字符串 "auto"，传
    {"type":"function","function":{"name":"lookup_order"}} 不会报错但会被
    静默当成 auto 处理，模型完全可能对无关问题跳过工具调用。
    所以这里**不依赖模型自觉**：代码里无条件先本地调用 lookup_order()，
    把结果作为上下文喂给模型；同时仍然把该函数注册为 tool，
    允许模型在需要查另一个订单号时再补查。
"""

import json
import os
import re
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
DEFAULT_ORDER_ID = "SO20260907001"
MAX_TOOL_ROUNDS = 3
TIMEOUT = 120


# --------------------------------------------------------------------------
# 本地工具实现（mock 数据）
# --------------------------------------------------------------------------

_MOCK_ORDERS = {
    "SO20260907001": {
        "order_id": "SO20260907001",
        "status": "运输中",
        "items": [{"name": "机械键盘 87 键", "qty": 1, "price": 399.00}],
        "total_amount": 399.00,
        "paid_at": "2026-09-05 10:12:33",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890123",
        "latest_track": "2026-09-07 08:41 快件已到达【杭州转运中心】",
        "estimated_delivery": "2026-09-08",
        "receiver": "张先生 / 杭州市西湖区文一西路 xxx 号",
    }
}


def lookup_order(order_id: str) -> dict:
    """查询订单详情。真实业务里这里应该打订单系统的接口，这里返回 mock 数据。"""
    # 硬性要求：每次被调用都往 stderr 打一行，方便确认它真的被调了
    print("[TOOL] lookup_order called", file=sys.stderr, flush=True)

    order_id = (order_id or "").strip() or DEFAULT_ORDER_ID
    order = _MOCK_ORDERS.get(order_id.upper())
    if order is None:
        return {
            "order_id": order_id,
            "found": False,
            "message": "未查询到该订单号对应的订单，请核对订单号是否正确。",
        }
    result = dict(order)
    result["found"] = True
    return result


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "查询订单详情（状态、物流轨迹、金额、预计送达时间等）。"
            "当需要确认另一个订单号的信息时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 SO20260907001；不确定时传空字符串表示查当前默认订单。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "你是一家电商公司的在线客服助手，说话简洁、友好、口语化，用中文回答。\n"
    "回答规则：\n"
    "1. 系统已经替你查过当前用户的订单，订单数据在下一条消息里，请**基于这份真实数据**回答，"
    "不要编造订单号、物流公司、单号或时间。\n"
    "2. 如果用户的问题和订单无关（比如问退换货政策、闲聊），也要正常回答，"
    "并在合适时自然地提一句当前订单的状态。\n"
    "3. 如果用户提到了另一个订单号，调用 lookup_order 工具去查，不要猜。\n"
    "4. 不要输出 JSON 或工具调用细节，直接给用户看得懂的自然语言回答。"
)


# --------------------------------------------------------------------------
# API 调用
# --------------------------------------------------------------------------


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def chat(messages: list, api_key: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        # 智谱只支持 tool_choice="auto"，强制指定函数无效，这里不做无用功
        "tool_choice": "auto",
        # glm-5.3 在标准端点强制开启思考，传 thinking.disabled 会报 1210，
        # 只能用 reasoning_effort 调节强度；客服场景用 low 降延迟。
        "reasoning_effort": "low",
        "stream": False,
    }
    resp = requests.post(BASE_URL, headers=_headers(api_key), json=payload, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"智谱 API 返回 HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def extract_order_id(text: str) -> str:
    """从用户消息里尽量抠出订单号，抠不到就用默认订单。"""
    m = re.search(r"\b([A-Za-z]{2,4}\d{6,})\b", text)
    if m:
        return m.group(1).upper()
    m = re.search(r"订单\s*(?:号)?\s*[:：]?\s*([A-Za-z0-9]{6,})", text)
    if m:
        return m.group(1).upper()
    return DEFAULT_ORDER_ID


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python3 main.py "我的订单到哪了"', file=sys.stderr)
        return 2
    user_message = " ".join(sys.argv[1:]).strip()

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY。", file=sys.stderr)
        return 2

    # ===== 硬性业务要求：回答之前无条件先查一次订单 =====
    order_id = extract_order_id(user_message)
    order_info = lookup_order(order_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "【系统已查询到的当前订单数据】\n"
            + json.dumps(order_info, ensure_ascii=False, indent=2),
        },
        {"role": "user", "content": user_message},
    ]

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = chat(messages, api_key)
            message = result["choices"][0]["message"]
            # assistant 消息必须原样（含 tool_calls）加回历史，顺序不能乱
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = (message.get("content") or "").strip()
                print(content if content else "（模型未返回内容，请稍后重试）")
                return 0

            for tool_call in tool_calls:
                if tool_call.get("type") != "function":
                    continue
                fn = tool_call.get("function") or {}
                if fn.get("name") != "lookup_order":
                    tool_result = {"error": f"未知工具: {fn.get('name')}"}
                else:
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_result = lookup_order(str(args.get("order_id") or order_id))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        print("（工具调用轮次过多，未能生成最终回答，请重试）", file=sys.stderr)
        return 1

    except requests.RequestException as exc:
        print(f"请求智谱 API 失败：{exc}", file=sys.stderr)
        return 1
    except (RuntimeError, KeyError, IndexError, ValueError) as exc:
        print(f"处理智谱 API 响应失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
