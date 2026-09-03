#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
客服工单机器人 —— 强制先查订单状态，再回答用户。

============================================================================
为什么不能只靠 "tool_choice" 强制模型调用工具？
============================================================================
智谱 GLM 的 /paas/v4/chat/completions 接口里，`tool_choice` 目前**只支持
字符串 "auto"**，不支持像 OpenAI 那样传
`{"type": "function", "function": {"name": "lookup_order"}}` 去强制模型
必须调用某个指定函数（参见 bigmodel-cn 技能包 references/chat.md 第 436
行的实测结论："tool_choice 目前默认且仅支持字符串 auto（不支持强制指定某个
函数）"）。

也就是说：**"模型必须先调用 lookup_order 再回答" 这件事，GLM 的 API 本身
没有任何参数能保证**——就算 system prompt 里写得再狠，模型也有一定概率
"忘记"调用工具、或者对它认为"无关"的问题直接跳过工具直接回答（尤其是像
"你是谁""今天天气怎么样"这种和订单看起来无关的问题，模型更容易跳过）。

============================================================================
本脚本的解决方案：把"强制调用"从"祈求模型"变成"代码本身去做"
============================================================================
既然 API 不提供强制单函数调用，那就不要把这件事的"保证"寄托在模型的自觉性
上。本脚本的做法是：

  1. 每一轮用户消息进来后，**不问模型的意见**，由 Python 代码无条件执行
     真正的 lookup_order(order_id) 查询；
  2. 把这次查询伪装成一次"标准的 function-calling 回合"写回对话历史：
     先追加一条 assistant 消息（携带我们自己构造的 tool_calls），再追加一条
     对应的 role="tool" 消息（内容是真实查询结果，tool_call_id 与上一步
     对齐）；
  3. 然后才把完整对话历史发给 GLM，让它基于"已经查到的订单状态"生成最终的
     自然语言回复。

因为 GLM 的 chat/completions 接口是无状态的——每次请求都是把完整的
messages 数组当作"历史"发过去，接口本身并不会去校验某条 assistant 消息
里的 tool_calls 是否真的是"上一次模型自己返回的"。所以我们完全可以在应用层
"代替"模型完成这次工具调用，模型看到的历史和它自己老老实实调用了一次工具
是一模一样的。

这样一来："先查订单"这个约束就从"模型今天心情好不好、prompt 写得够不够
狠"变成了"Python 代码里一个无条件执行的函数调用"——不管用户说什么（哪怕是
和订单完全无关的闲聊、抱怨、离题问题），lookup_order 都 100% 会在模型生成
任何面向用户的自然语言回复之前被执行一次。这是一个确定性的代码路径，不是
一个依赖模型服从指令概率的软约束。

之后模型自己是否想再调用一次 lookup_order（比如用户话里提到了另一个订单
号）我们仍然照常支持（标准 function-calling 循环），只是"第一次、必须的
那一次"不再赌模型愿不愿意配合。

============================================================================
运行方式
============================================================================
    export ZHIPUAI_API_KEY="你的真实 API Key"   # 从 bigmodel.cn 控制台获取
    python order_bot.py                          # 进入交互式命令行
    python order_bot.py --order-id SF202409030001  # 预置本次会话的订单号

注意：本文件里的 API Key 一律从环境变量读取，不在代码中硬编码。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

# ============================================================================
# 一、平台接入配置（来自 bigmodel-cn 技能包 SKILL.md / references/chat.md）
# ============================================================================

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"  # 永远不要把 Key 硬编码进代码
MODEL = "glm-5.2"  # 支撑复杂长程任务 / 工具调用能力较强的 GLM 版本
REQUEST_TIMEOUT = 30  # 秒
MAX_RETRIES = 3  # 仅对 429 / 5xx 做指数退避重试；4xx 配置错误不重试
MAX_TOOL_LOOP = 4  # 模型自主追加工具调用的最大轮数，防止死循环


# ============================================================================
# 二、lookup_order 工具的真实实现（Demo 用本地模拟数据，接口保持不变，
#    生产环境把函数体换成真正调用订单系统的 HTTP/RPC 客户端即可）
# ============================================================================

MOCK_ORDER_DB: Dict[str, Dict[str, Any]] = {
    "SF202409030001": {
        "status": "已发货",
        "carrier": "顺丰速运",
        "tracking_no": "SF1234567890",
        "eta": "2026-09-05",
        "amount": 299.00,
    },
    "JD1002003004": {
        "status": "待发货",
        "carrier": None,
        "tracking_no": None,
        "eta": None,
        "amount": 158.50,
    },
    "TB88889999": {
        "status": "已签收",
        "carrier": "中通快递",
        "tracking_no": "ZTO9988776655",
        "eta": "2026-08-30",
        "amount": 899.00,
    },
}


def lookup_order(order_id: Optional[str]) -> Dict[str, Any]:
    """查询订单状态。

    这是本机器人唯一声明的工具。真实项目里应替换成对订单/物流系统的
    HTTP 调用（例如 requests.get("https://your-order-api/orders/{id}")），
    这里为了保证脚本无需任何外部依赖、任何人都能直接跑通，用一份内存里的
    模拟订单数据代替。
    """
    if not order_id or order_id.upper() == "UNKNOWN":
        return {
            "found": False,
            "order_id": order_id,
            "message": "未识别到有效订单号，请提供订单号（例如 SF202409030001）以便查询。",
        }

    order = MOCK_ORDER_DB.get(order_id.upper())
    if order is None:
        return {
            "found": False,
            "order_id": order_id,
            "message": f"未查询到订单号为 {order_id} 的订单，请确认订单号是否正确。",
        }

    return {"found": True, "order_id": order_id.upper(), **order}


# 提供给 GLM 的工具定义（JSON Schema）。即便我们在应用层已经无条件执行了
# 一次强制查询，仍然把它注册在 tools 里——这样模型在后续对话中如果识别到
# 用户提供了新的/不同的订单号，依然可以按标准 function-calling 流程再次
# 主动调用它。
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "查询指定订单号的当前状态、物流商、运单号、预计送达时间与订单金额。"
                "任何涉及订单、物流、退款、催单的问题，回答前都必须先调用本工具确认"
                "订单的最新状态，禁止凭猜测或历史记忆回答订单状态。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 SF202409030001。",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]


# ============================================================================
# 三、从用户文本里尽力提取订单号（辅助功能，不是"是否查询"的判断依据——
#    不管有没有提取到订单号，lookup_order 都会被无条件调用一次）
# ============================================================================

# 形如 "订单号：SF202409030001" / "order id SF202409030001" / "订单 SF202409030001"
_LABELED_ORDER_ID_RE = re.compile(
    r"(?:订单(?:号|编号)?|order\s*(?:id|no\.?|number)?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9\-]{4,29})",
    re.IGNORECASE,
)
# 兜底：一段看起来像订单号的裸字符串（字母+数字混合，长度较长，避免误伤普通数字）
_BARE_ORDER_ID_RE = re.compile(r"\b([A-Za-z]{1,4}\d{6,20}|\d{8,20})\b")


def extract_order_id(text: str) -> Optional[str]:
    for pattern in (_LABELED_ORDER_ID_RE, _BARE_ORDER_ID_RE):
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


# ============================================================================
# 四、GLM chat/completions 客户端（标准库 requests，直接调 HTTP 接口）
# ============================================================================


class GLMError(RuntimeError):
    """GLM API 调用失败（含 HTTP 错误、业务错误码、响应格式异常）。"""


class GLMClient:
    def __init__(self, api_key: str, model: str = MODEL, base_url: str = BASE_URL):
        if not api_key:
            raise ValueError(
                f"缺少 API Key，请先设置环境变量 {API_KEY_ENV_VAR}（从 "
                "https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）。"
            )
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            # 注意：GLM 的 tool_choice 目前只支持 "auto"，不支持强制指定某个
            # function，这正是本脚本要在应用层自行"代为调用"lookup_order 的
            # 根本原因（见文件头部说明）。
            payload["tool_choice"] = tool_choice

        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(
                    self.base_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                self._backoff_sleep(attempt)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                # 限流 / 平台过载 / 服务端错误 —— 指数退避后重试
                last_exc = GLMError(
                    f"GLM API 返回可重试错误 HTTP {resp.status_code}: {resp.text[:500]}"
                )
                self._backoff_sleep(attempt)
                continue

            if resp.status_code >= 400:
                # 4xx 多是参数/鉴权/欠费类配置问题，重试没有意义，直接抛出
                raise GLMError(
                    f"GLM API 请求失败 HTTP {resp.status_code}: {resp.text[:500]}"
                )

            data = resp.json()
            if isinstance(data, dict) and "error" in data:
                raise GLMError(f"GLM API 返回业务错误: {data['error']}")
            return data

        raise GLMError(f"GLM API 多次重试后仍然失败: {last_exc}") from last_exc

    @staticmethod
    def _backoff_sleep(attempt: int) -> None:
        time.sleep(min(2 ** attempt, 10))


# ============================================================================
# 五、工单机器人主逻辑
# ============================================================================

SYSTEM_PROMPT = """你是「示例科技」的智能客服工单机器人，专门处理与订单相关的售后与咨询问题。

重要规则：
1. 在你看到这轮对话之前，系统已经代表你调用了 lookup_order 工具查询了当前
   会话关联订单的最新状态，查询结果会作为一条 role=tool 的消息出现在对话
   历史里。你必须基于这份真实数据回答，不允许凭猜测或记忆编造订单状态。
2. 如果 lookup_order 返回 found=false，说明还没有拿到有效订单号，或者该
   订单号查不到。这种情况下你应该礼貌地请用户提供正确的订单号，而不是绕开
   这件事直接回答用户提出的其他问题。
3. 如果用户这句话看起来和订单无关（比如打招呼、闲聊、问你是谁、问天气），
   也请先简短确认一下当前订单状态查询的结果（因为系统已经查过了，不要假装
   没查过），再礼貌回应用户的话题，并适度引导用户回到工单场景。
4. 如果用户在对话中提到了另一个订单号，你可以主动再次调用 lookup_order
   查询这个新订单号。
5. 保持简洁、专业、有礼貌的客服语气，使用中文回复。
"""


class OrderSupportBot:
    def __init__(self, client: GLMClient, initial_order_id: Optional[str] = None):
        self.client = client
        self.session_order_id: Optional[str] = (
            initial_order_id.upper() if initial_order_id else None
        )
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    # -- 核心保证：无条件、代码强制执行一次 lookup_order -------------------
    def _force_lookup_order(self, order_id: str) -> None:
        """不经过模型决策，直接在代码里执行一次订单查询，并把它写成一次
        看起来"完全正常"的 function-calling 回合追加进对话历史。

        这是本脚本"保证工具一定被调用"的唯一来源，与模型是否听话、
        system prompt 写得好不好完全无关。
        """
        call_id = f"call_forced_{uuid.uuid4().hex[:24]}"
        forced_tool_call = {
            "id": call_id,
            "type": "function",
            "function": {
                "name": "lookup_order",
                "arguments": json.dumps({"order_id": order_id}, ensure_ascii=False),
            },
        }
        self.messages.append(
            {"role": "assistant", "content": None, "tool_calls": [forced_tool_call]}
        )

        try:
            result = lookup_order(order_id)
        except Exception as exc:  # noqa: BLE001
            # 查询失败也绝不能"静默跳过"——把失败结果照样写回上下文，
            # 让模型知道查询失败了，而不是让它在没有任何订单信息的情况下
            # 自由发挥。
            result = {
                "found": False,
                "order_id": order_id,
                "message": f"订单查询服务异常：{exc}",
            }

        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    # -- 强制查询之后，走标准 function-calling 循环拿模型的最终自然语言回复 --
    def _run_model_loop(self) -> str:
        for _ in range(MAX_TOOL_LOOP):
            data = self.client.chat(self.messages, tools=TOOLS, tool_choice="auto")
            choices = data.get("choices") or []
            if not choices:
                raise GLMError(f"GLM API 响应缺少 choices 字段: {data}")

            message = choices[0]["message"]
            self.messages.append(message)

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content") or ""

            for tool_call in tool_calls:
                fn = tool_call.get("function", {})
                if tool_call.get("type") == "function" and fn.get("name") == "lookup_order":
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    order_id = args.get("order_id") or self.session_order_id or "UNKNOWN"
                    try:
                        result = lookup_order(order_id)
                    except Exception as exc:  # noqa: BLE001
                        result = {
                            "found": False,
                            "order_id": order_id,
                            "message": f"订单查询服务异常：{exc}",
                        }
                    if result.get("found"):
                        self.session_order_id = result["order_id"]
                else:
                    result = {"error": f"未知或不支持的工具: {fn.get('name')}"}

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return "抱歉，这次请求需要的工具调用次数过多，请稍后再试或转接人工客服。"

    def handle_user_message(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})

        extracted = extract_order_id(user_text)
        if extracted:
            self.session_order_id = extracted

        order_id_for_lookup = self.session_order_id or "UNKNOWN"

        # 不管 user_text 里说的是什么——包括完全和订单无关的内容——都无条件
        # 先查一次订单状态，再进入正常的模型问答流程。
        self._force_lookup_order(order_id_for_lookup)

        return self._run_model_loop()


# ============================================================================
# 六、命令行入口
# ============================================================================


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="客服工单机器人（强制先查订单状态）")
    parser.add_argument(
        "--order-id",
        default=None,
        help="预置本次会话关联的订单号（可选，用户后续也可以在对话中提供/更新）。",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"使用的 GLM 模型名称，默认 {MODEL}。",
    )
    parser.add_argument(
        "--api-key-env",
        default=API_KEY_ENV_VAR,
        help=f"读取 API Key 的环境变量名，默认 {API_KEY_ENV_VAR}。",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    api_key = os.environ.get(args.api_key_env, "")

    try:
        client = GLMClient(api_key=api_key, model=args.model)
    except ValueError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        sys.exit(1)

    bot = OrderSupportBot(client, initial_order_id=args.order_id)

    print("客服工单机器人已启动（输入 exit / quit 退出）。")
    print("提示：无论你说什么，机器人在回复前都会先强制查询一次订单状态。\n")

    while True:
        try:
            user_text = input("用户> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit", "退出"}:
            break

        try:
            reply = bot.handle_user_message(user_text)
        except GLMError as exc:
            print(f"[机器人调用出错] {exc}")
            continue

        print(f"机器人> {reply}\n")


if __name__ == "__main__":
    main()
