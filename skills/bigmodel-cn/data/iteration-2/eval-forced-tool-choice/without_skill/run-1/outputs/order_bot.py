#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
order_bot.py — 客服工单机器人（智谱 GLM-5.3）

设计目标
--------
不管用户说什么（哪怕是与订单完全无关的问题），机器人在给出任何回答之前，
都必须先调用 lookup_order(order_id) 工具查询一次订单状态。绝不允许模型
"跳过工具调用、直接自由作答"。

实现思路：双重保险（模型层 + 代码层）
--------------------------------------
1. 模型层强制：每个用户回合的第一次 LLM 请求，显式传入
       tool_choice = {"type": "function", "function": {"name": "lookup_order"}}
   这是 OpenAI 兼容协议（智谱 GLM 的 /chat/completions 接口兼容此协议）里
   "强制调用指定函数" 的标准写法。模型收到这个参数后，本轮 completion
   *只能* 产出对 lookup_order 的 tool_call，不能直接输出文本答案。

2. 代码层兜底：即便强制参数生效，我们也不"信任"模型一定老实听话
   （不同网关/模型版本对该参数的支持程度可能不同）。收到响应后，
   代码显式检查 message.tool_calls 是否存在、且第一个 tool_call 的
   函数名是否为 "lookup_order"：
       - 如果不满足，判定为"模型试图跳过工具调用"，直接抛出
         ForcedToolCallViolation 异常并中止本轮——绝不会把模型此时
         附带的任何 content 文本当作答案返回给用户。
       - 只有在工具调用被真正执行、拿到订单数据之后，代码才会发起
         第二次 LLM 请求（不强制工具、只要求基于订单数据自然语言作答），
         这次的输出才会被返回给用户。

   换句话说："先查订单"这一步不是靠 prompt 里的一句话说服模型，而是
   由请求参数 + 响应校验在代码层面强制保证，模型没有绕过的机会。

3. order_id 从哪里来：这是一次客服工单会话，通常整通对话都是围绕一个
   已知工单/订单展开的。order_id 的解析优先级为：
       a) 用户本条消息中用正则提取到的订单号（如 "ORD20240501" "订单号12345"）
       b) 会话里此前已经解析到的 order_id（记在 self.current_order_id）
       c) 都没有则使用占位符 "UNKNOWN"，仍然照常调用 lookup_order("UNKNOWN")，
          工具会返回"未找到订单"，随后模型基于这个结果回复用户，引导其
          提供订单号——但"调用工具"这个动作本身永远不会被跳过。

依赖：仅使用标准库 + requests（不使用智谱官方 SDK）。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 智谱开放平台 v4 接口地址（OpenAI 兼容的 chat/completions）
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型名称。按任务要求使用 GLM-5.3。
GLM_MODEL = "glm-5.3"

# API Key 从环境变量读取，不在代码里硬编码任何真实密钥。
# 智谱 v4 接口支持直接把 "API Key" 作为 Bearer Token 使用。
API_KEY_ENV_VAR = "ZHIPU_API_KEY"
API_KEY = os.environ.get(API_KEY_ENV_VAR, "PLACEHOLDER_API_KEY_SET_ZHIPU_API_KEY_ENV")

REQUEST_TIMEOUT_SECONDS = 30
MAX_FORCED_CALL_RETRIES = 2  # 强制工具调用若异常失败，允许的重试次数


class ForcedToolCallViolation(RuntimeError):
    """模型在被强制要求调用 lookup_order 时，未按预期产出工具调用。"""


# --------------------------------------------------------------------------
# 工具（tool）定义：lookup_order
# --------------------------------------------------------------------------

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "查询指定订单当前的状态、物流信息与基本信息。"
                "任何客服回复在给出结论前都必须先调用本工具获取最新订单状态。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单编号，例如 'ORD20240501' 或 '12345'。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

FORCED_TOOL_CHOICE = {"type": "function", "function": {"name": "lookup_order"}}


# --------------------------------------------------------------------------
# lookup_order 的本地实现（模拟订单系统；如需接入真实系统，
# 替换为对内部订单服务的 HTTP 调用即可，接口形状保持不变）
# --------------------------------------------------------------------------

_MOCK_ORDER_DB: Dict[str, Dict[str, Any]] = {
    "ORD20240501": {
        "order_id": "ORD20240501",
        "status": "已发货",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890",
        "estimated_delivery": "2026-09-05",
        "amount": 299.00,
        "currency": "CNY",
    },
    "12345": {
        "order_id": "12345",
        "status": "待付款",
        "carrier": None,
        "tracking_no": None,
        "estimated_delivery": None,
        "amount": 88.00,
        "currency": "CNY",
    },
}


def lookup_order(order_id: str) -> Dict[str, Any]:
    """查询订单状态。真实场景中应替换为对内部订单系统的 HTTP/RPC 调用。"""
    order = _MOCK_ORDER_DB.get(order_id)
    if order is None:
        return {
            "order_id": order_id,
            "found": False,
            "message": "未找到该订单号，请确认订单号是否正确。",
        }
    return {"found": True, **order}


# --------------------------------------------------------------------------
# 从用户消息中尝试提取订单号
# --------------------------------------------------------------------------

_ORDER_ID_PATTERNS = [
    re.compile(r"\bORD\d{5,}\b", re.IGNORECASE),
    re.compile(r"订单[号编]?[:：\s]*([A-Za-z0-9]{4,})"),
    re.compile(r"\b\d{5,}\b"),
]


def extract_order_id(text: str) -> Optional[str]:
    for pattern in _ORDER_ID_PATTERNS:
        m = pattern.search(text)
        if m:
            # 部分正则捕获组是整段匹配，部分是子组
            return m.group(1) if m.groups() else m.group(0)
    return None


# --------------------------------------------------------------------------
# 智谱 GLM HTTP 客户端（纯 requests，不用官方 SDK）
# --------------------------------------------------------------------------


class GLMClient:
    def __init__(self, api_key: str, api_url: str = GLM_API_URL, model: str = GLM_MODEL):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        temperature: float = 0.3,
    ) -> Dict[str, Any]:
        """向 GLM 的 chat/completions 接口发起一次请求，返回原始 JSON。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        response = requests.post(
            self.api_url,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()


# --------------------------------------------------------------------------
# 工单机器人主逻辑
# --------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是一个电商客服工单机器人。你的唯一订单查询手段是 lookup_order 工具。"
    "系统会在每一轮用户发言后，强制先为你调用一次 lookup_order 获取该订单的最新状态，"
    "然后把查询结果作为上下文提供给你。你必须基于该结果回答用户，"
    "禁止在没有拿到 lookup_order 结果之前对订单状态做任何猜测或编造。"
    "如果用户的问题与订单无关，也请先礼貌回应，并在合适的地方提及当前订单的最新状态。"
)


class OrderSupportBot:
    def __init__(self, client: GLMClient):
        self.client = client
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.current_order_id: Optional[str] = None

    def _resolve_order_id(self, user_text: str) -> str:
        extracted = extract_order_id(user_text)
        if extracted:
            self.current_order_id = extracted
            return extracted
        if self.current_order_id:
            return self.current_order_id
        return "UNKNOWN"

    def _force_lookup_order_call(self, order_id_hint: str) -> Dict[str, Any]:
        """
        第一次 LLM 请求：强制模型只能调用 lookup_order。
        代码层校验响应中确实包含对 lookup_order 的 tool_call，
        否则视为"试图跳过工具调用"，直接报错，绝不把此次响应的文本内容
        当作最终答案使用。
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_FORCED_CALL_RETRIES + 2):
            # 在最后一次系统消息里提示当前应查询的订单号，帮助模型正确填参数，
            # 但即便模型填错/漏填，我们也不依赖它——下面会用 order_id_hint 兜底。
            hint_messages = self.messages + [
                {
                    "role": "system",
                    "content": (
                        f"[内部提示] 本轮请先调用 lookup_order 查询订单号 "
                        f"'{order_id_hint}' 的状态。"
                    ),
                }
            ]

            try:
                raw = self.client.chat(
                    messages=hint_messages,
                    tools=TOOLS_SCHEMA,
                    tool_choice=FORCED_TOOL_CHOICE,
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(0.5)
                continue

            choice = (raw.get("choices") or [{}])[0]
            message = choice.get("message", {}) or {}
            tool_calls = message.get("tool_calls") or []

            if not tool_calls or tool_calls[0].get("function", {}).get("name") != "lookup_order":
                # 模型没有按要求调用工具——绝不接受它可能附带的自由文本回答。
                last_error = ForcedToolCallViolation(
                    "模型未按强制要求调用 lookup_order 工具，本次响应已被丢弃。"
                    f" 原始 message = {message!r}"
                )
                time.sleep(0.5)
                continue

            # 成功：拿到了合法的强制工具调用
            self.messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            return tool_calls[0]

        # 多次重试后仍未拿到工具调用：中止本轮，绝不返回未经工具核实的答案。
        assert last_error is not None
        raise ForcedToolCallViolation(
            "多次尝试后模型仍未产出对 lookup_order 的强制工具调用，"
            "为避免绕过订单查询直接作答，本轮请求已终止。"
        ) from last_error

    def _execute_tool_call(self, tool_call: Dict[str, Any], fallback_order_id: str) -> None:
        args_raw = tool_call.get("function", {}).get("arguments") or "{}"
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args = {}

        order_id = args.get("order_id") or fallback_order_id
        result = lookup_order(order_id)

        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    def _generate_final_reply(self) -> str:
        """
        第二次 LLM 请求：此时订单数据已经在上下文里，
        禁止再调用任何工具（tool_choice="none"），只要求基于已查到的
        订单信息生成面向用户的自然语言回复。
        """
        raw = self.client.chat(
            messages=self.messages,
            tools=TOOLS_SCHEMA,
            tool_choice="none",
        )
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        content = message.get("content") or ""

        self.messages.append({"role": "assistant", "content": content})
        return content

    def handle_user_message(self, user_text: str) -> str:
        """
        处理一轮用户输入。无论用户说什么，都会先强制触发一次
        lookup_order 调用，再基于查询结果生成回复。
        """
        self.messages.append({"role": "user", "content": user_text})

        order_id_hint = self._resolve_order_id(user_text)

        # 第一步：强制调用 lookup_order（模型层强制 + 代码层校验，双重保证）
        tool_call = self._force_lookup_order_call(order_id_hint)

        # 第二步：真正在本地/内部系统执行查询
        self._execute_tool_call(tool_call, fallback_order_id=order_id_hint)

        # 第三步：基于查询结果生成给用户的最终回答
        return self._generate_final_reply()


# --------------------------------------------------------------------------
# CLI 演示入口
# --------------------------------------------------------------------------


def main() -> None:
    if API_KEY.startswith("PLACEHOLDER_"):
        print(
            f"[警告] 未检测到有效的 API Key，请先设置环境变量 {API_KEY_ENV_VAR}。\n"
            "当前使用的是占位符密钥，实际请求会因鉴权失败而报错，"
            "但脚本的工具强制调用逻辑本身是完整可运行的。\n",
            file=sys.stderr,
        )

    client = GLMClient(api_key=API_KEY)
    bot = OrderSupportBot(client)

    print("客服工单机器人已启动（输入 exit / quit 退出）。")
    print("提示：无论你问什么，机器人都会先调用 lookup_order 查询订单状态。\n")

    while True:
        try:
            user_text = input("用户> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break

        try:
            reply = bot.handle_user_message(user_text)
        except ForcedToolCallViolation as exc:
            print(f"[系统] 已阻止一次未经工具核实的回答：{exc}")
            continue
        except requests.RequestException as exc:
            print(f"[系统] 调用智谱 GLM API 失败：{exc}")
            continue

        print(f"客服> {reply}\n")


if __name__ == "__main__":
    main()
