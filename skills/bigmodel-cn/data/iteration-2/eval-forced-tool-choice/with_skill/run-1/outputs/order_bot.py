#!/usr/bin/env python3
"""
客服工单机器人（Order Support Bot）
====================================

需求：不管用户说什么，机器人在生成任何自由文本回答之前，都必须先调用
`lookup_order(order_id)` 查询一次订单状态，绝对不能让大模型"跳过"这一步。

模型：智谱 GLM-5.3（bigmodel.cn / open.bigmodel.cn）
HTTP 方式：仅用标准库 `requests` 直接调 `POST /paas/v4/chat/completions`，
不依赖 zhipuai / openai 等任何 SDK。

── 关键设计决策（请务必阅读同目录 notes.md）──────────────────────────
智谱 `chat/completions` 接口的 `tool_choice` 字段【只支持字符串 "auto"】，
不支持像 OpenAI 那样传 `{"type": "function", "function": {"name": "..."}}`
来强制模型必须调用某个指定函数（见 references/chat.md 第四节）。

也就是说：**无法用 API 参数从服务端强制"这一轮必须调用 lookup_order"**。
如果单纯把 lookup_order 注册为一个 tool，然后寄希望于模型"自觉"调用它，
模型完全可能对无关问题（"你好" "今天星期几"）直接跳过工具调用，直接用
自然语言回答——这正是需求明确禁止的行为。

因此本脚本把"强制调用"从"祈求模型履约"改成"应用层代码兜底"：
    1. 每一轮用户消息进来后，脚本【无条件】在本地直接调用真正的
       `lookup_order(order_id)` 函数（不经过模型），拿到订单查询结果。
    2. 再把这次调用伪装成一轮标准的 OpenAI 兼容 function-calling 回合，
       手工拼出 `{"role": "assistant", "tool_calls": [...]}` +
       `{"role": "tool", "tool_call_id": ..., "content": ...}` 两条消息，
       追加进对话历史（这是 chat.md 里描述的标准 tool 消息结构，只是
       这次"发起调用"的不是模型，而是我们自己的代码）。
    3. 然后才第一次把完整历史发给 GLM-5.3，让它基于已经写入上下文的
       真实订单数据生成回答。

这样，模型根本没有机会在"看到工具结果之前"就抢答——因为它压根不会被
问到"要不要调用工具"，调用这件事已经在代码里无条件发生了。这是比
"死磕 tool_choice 强制参数"更可靠的工程手段，代价是：模型自己想额外
调用 lookup_order（例如用户话里换了一个新订单号）需要脚本自己解析
新订单号并再次触发同样的强制流程，而不是放任模型自由决定要不要调用。
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests

# ── 智谱开放平台配置 ────────────────────────────────────────────────
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

# API Key 必须从环境变量读取，绝不硬编码。
# 控制台获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

REQUEST_TIMEOUT = 60  # 秒
MAX_TOOL_ROUNDS = 4  # 防止模型在后续轮次里陷入工具调用死循环的安全上限


def _get_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"未找到环境变量 {API_KEY_ENV_VAR}。请先执行：\n"
            f'  export {API_KEY_ENV_VAR}="your-real-api-key"\n'
            "（本脚本中的默认值只是占位符，不会拿去真实调用。）"
        )
    return api_key


# ── lookup_order 工具：真实业务函数 + 对外暴露给模型的 JSON Schema ──────

# lookup_order 提供给模型的 function-calling 声明。即便调用本身是代码强制
# 触发的，仍然把 schema 注册进 `tools`，这样：
#   1) 模型能在最终回答里正确理解 tool 消息里那份订单数据的字段含义；
#   2) 如果用户在对话中途报出一个新订单号，模型在后续轮次仍可以（在
#      tool_choice="auto" 下）主动再调用一次 lookup_order，脚本会照常
#      执行真实查询并把结果写回去（见 chat() 循环的第 4 步）。
LOOKUP_ORDER_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "根据订单号查询订单的当前状态、物流信息与基本商品信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "订单号，例如 SO-20260901-0001",
                }
            },
            "required": ["order_id"],
        },
    },
}

_MOCK_STATUSES = [
    "待付款",
    "待发货",
    "已发货，运输中",
    "已签收",
    "已取消",
    "退款处理中",
]


def lookup_order(order_id: str) -> dict[str, Any]:
    """查询订单状态。

    这是本机器人【唯一被强制、无条件调用】的工具函数。

    真实生产环境中，这里应该是对内部订单服务发起一次 HTTP 调用，例如：

        resp = requests.get(
            f"{ORDER_SERVICE_BASE_URL}/orders/{order_id}",
            headers={"Authorization": f"Bearer {ORDER_SERVICE_TOKEN}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    题目明确要求"不要实际调用真实外部接口"，且这里也没有真实的订单后端，
    所以用一个确定性的本地 mock 来代替，但函数签名、返回结构与"这一步
    必须发生"的行为是完全真实可用的——接入真实订单系统时只需替换函数体。
    """
    order_id = (order_id or "").strip()

    if not order_id or order_id.upper() == "UNKNOWN":
        return {
            "order_id": order_id or None,
            "found": False,
            "error": "未能从用户消息中识别出有效订单号，请引导用户提供订单号。",
        }

    # 用订单号做随机种子，保证同一个订单号每次查询返回一致的状态，
    # 方便人工测试/复现问题。
    rng = random.Random(order_id)
    status = rng.choice(_MOCK_STATUSES)

    return {
        "order_id": order_id,
        "found": True,
        "status": status,
        "items": [{"name": "示例商品 A", "qty": 1}],
        "last_update": "2026-09-02T18:30:00+08:00",
        "courier": "示例快递" if "发货" in status or "签收" in status else None,
        "note": "（mock 数据，接入真实订单系统时替换 lookup_order 函数体）",
    }


# ── 从用户消息中提取订单号（尽力而为，不是本设计的强制点）────────────

# 支持形如 SO-20260901-0001 / ORD123456 / DD20260901001 等常见订单号格式，
# 以及一段 6~20 位的纯数字，作为兜底。识别不到时返回 None，交由
# lookup_order 自己返回"未找到订单号"的结果，而不是让脚本自己拒绝调用——
# 因为本设计的核心承诺是"这一步必须发生"，即使参数不完整也要发生。
_ORDER_ID_PATTERNS = [
    re.compile(r"\b[A-Za-z]{1,4}-?\d{6,15}(?:-\d{1,6})?\b"),
    re.compile(r"\b\d{6,20}\b"),
]


def extract_order_id(text: str) -> str | None:
    for pattern in _ORDER_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


# ── 会话与消息历史 ──────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "你是一个电商平台的客服工单机器人。你的每一轮回答都必须建立在对话历史里"
    "已经出现的 lookup_order 工具返回结果之上——那是当前订单最新、最权威的"
    "真实数据，不允许凭空猜测或编造订单状态。\n"
    "- 如果工具结果里 found=false（没有识别到有效订单号），要礼貌地请用户"
    "提供订单号，而不是编造一个订单状态。\n"
    "- 如果用户问的问题和订单无关（例如寒暄、问天气），也要先简要确认一下"
    "当前工单关联订单的状态，再回答用户实际的问题；不要跳过订单状态播报。\n"
    "- 回答要简洁、口语化，使用中文。"
)


@dataclass
class OrderBot:
    """一个绑定到某个客服工单的机器人会话。

    `order_id` 是这张工单默认关联的订单号（例如工单系统在创建时就已经把
    用户和某个订单绑定），每一轮对话都会用它（或者用户新提到的订单号）
    去调用一次 lookup_order —— 与用户这句话到底问的是什么完全无关。
    """

    order_id: str | None = None
    api_key: str = field(default_factory=_get_api_key)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # -- 核心入口 ---------------------------------------------------
    def handle_user_message(self, user_text: str) -> str:
        """处理用户一句话，返回机器人的最终自然语言回答。

        无论 user_text 是什么内容，函数体的第一件事永远是
        `self._force_lookup_order(...)`——这就是"绝不能让模型跳过这一步"
        的落地方式：跳过与否根本不取决于模型，是 Python 控制流本身保证的。
        """
        self.messages.append({"role": "user", "content": user_text})

        # 1) 确定这一轮要查询的订单号：优先用用户这句话里新提到的订单号，
        #    否则回退到工单默认绑定的订单号。
        current_order_id = extract_order_id(user_text) or self.order_id or "UNKNOWN"
        if extract_order_id(user_text):
            # 用户显式提到了新订单号，之后的轮次也切换到这个订单上。
            self.order_id = current_order_id

        # 2) 无条件、强制地调用 lookup_order —— 不经过模型、不受
        #    tool_choice 限制，这一行本身就是保证。
        self._force_lookup_order(current_order_id)

        # 3) 只有工具结果已经写入历史之后，才第一次把对话交给模型。
        return self._run_model_turn()

    # -- 强制工具调用：手工拼出一轮标准的 function-calling 消息对 ------
    def _force_lookup_order(self, order_id: str) -> None:
        tool_call_id = f"call_{uuid.uuid4().hex[:24]}"
        arguments = json.dumps({"order_id": order_id}, ensure_ascii=False)

        # 真正执行查询（这是唯一有副作用的一步；其余都是把结果誊写进
        # 符合 chat.md 规范的 messages 结构）。
        result = lookup_order(order_id)

        # 3.a 先追加一条"assistant 发起了 tool_calls"的消息。
        #     按接口要求，携带 tool_calls 时 content 应为 null。
        self.messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "lookup_order",
                            "arguments": arguments,
                        },
                    }
                ],
            }
        )

        # 3.b 再追加对应的 tool 结果消息，tool_call_id 必须与上面对齐。
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    # -- 调用 GLM-5.3，并处理模型此后可能主动发起的（可选）工具调用 ----
    def _run_model_turn(self) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for _round in range(MAX_TOOL_ROUNDS):
            payload = {
                "model": MODEL,
                "messages": self.messages,
                "tools": [LOOKUP_ORDER_TOOL_SCHEMA],
                # tool_choice 目前智谱只支持字符串 "auto"（不支持强制指定
                # 某个函数），这里用默认值即可——反正第一次强制调用已经在
                # _force_lookup_order 里完成了，这里的 auto 只是允许模型
                # 在需要时（比如用户又报了另一个订单号）自行再次调用。
                "tool_choice": "auto",
            }

            resp = requests.post(
                BASE_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            message = choice["message"]

            # 把模型返回的 assistant 消息原样加回历史（可能含 tool_calls）。
            self.messages.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content") or ""

            # 模型自己额外发起了工具调用（tool_choice=auto 下允许），
            # 逐个执行并把结果写回，然后进入下一轮请求模型做最终回答。
            for tool_call in tool_calls:
                fn = tool_call.get("function", {})
                if fn.get("name") != "lookup_order":
                    # 本机器人目前只暴露了这一个工具，理论上不会出现别的
                    # 名字；出现的话返回一个明确的错误信息给模型，避免
                    # 静默忽略。
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(
                                {"error": f"未知工具: {fn.get('name')}"},
                                ensure_ascii=False,
                            ),
                        }
                    )
                    continue

                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                order_id = args.get("order_id") or self.order_id or "UNKNOWN"

                result = lookup_order(order_id)
                self.order_id = order_id
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        # 极端情况下模型反复要求调用工具，超过安全上限则强制收尾，避免死循环。
        return "抱歉，查询遇到一些问题，请稍后再试或联系人工客服。"


def main() -> None:
    print("客服工单机器人（GLM-5.3）—— 输入 'exit' 或 'quit' 退出。")
    ticket_order_id = input("请输入本工单关联的订单号（可留空）：").strip() or None

    try:
        bot = OrderBot(order_id=ticket_order_id)
    except RuntimeError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        sys.exit(1)

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
            reply = bot.handle_user_message(user_text)
        except requests.HTTPError as exc:
            print(f"[请求失败] {exc}", file=sys.stderr)
            continue
        except requests.RequestException as exc:
            print(f"[网络错误] {exc}", file=sys.stderr)
            continue

        print(f"客服机器人: {reply}")


if __name__ == "__main__":
    main()
