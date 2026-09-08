#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客服工单处理：必须先产出结构化工单，再给用户回复。

业务硬性要求：
- 先产出一条结构化工单（两个字段：category 工单分类、summary 问题摘要）；
- 工单是后续流程的输入，拿不到工单就明确报错退出，不能只回一句安慰话。

设计说明（为什么不用 tools + tool_choice 强制调用，也不用 json_schema）：
- 智谱 chat/completions 的 tool_choice 目前仅支持字符串 "auto"；OpenAI 风格的
  {"type":"function","function":{"name":"create_ticket"}} 不会报错，但会被静默当成
  auto 处理，模型完全可能跳过工具调用（技能包已用真实 API 验证）。所以「工单必须
  产出」不依赖模型自觉，而是由代码结构保证：
    1) 无条件先调用 create_ticket()——用 response_format=json_object 做结构化抽取；
    2) 客户端 json.loads + 字段校验，失败重试兜底（json_object 不保证输出 100% 合法）；
    3) 只有拿到合法工单后才允许进入 compose_reply()，否则报错退出、不发任何回复。
- response_format 只有 text / json_object 两种取值，json_schema 不受支持（会被静默
  忽略），因此目标字段结构写进 system prompt，最终以客户端校验为准。
- glm-5.3 在标准端点强制开启思考（传 thinking.type=disabled 会报 1210），轻量任务
  用 reasoning_effort="low" 降档即可（glm-5.3 仅接受 low/high/max）。

运行方式：ZHIPUAI_API_KEY=你的Key python3 main.py
"""

import json
import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
USER_MESSAGE = "我上周买的耳机坏了，想退货"
MAX_TICKET_ATTEMPTS = 3  # json_object 模式下输出仍可能夹带杂文，留重试余量
REQUEST_TIMEOUT = 60

TICKET_SYSTEM_PROMPT = (
    "你是客服工单系统的信息抽取模块。请根据用户消息生成一条结构化工单，"
    "只输出一个 JSON 对象，禁止输出任何解释性文字或代码块标记。格式：\n"
    '{"category": "<工单分类>", "summary": "<问题摘要>"}\n'
    "字段要求：\n"
    "- category：从这些分类中选最贴切的一个：退货退款、售后维修、商品质量、"
    "物流查询、账户问题、其他\n"
    "- summary：一句话客观概括用户的问题和诉求，不超过 40 个字"
)

REPLY_SYSTEM_PROMPT_TEMPLATE = (
    "你是一名电商平台的在线客服。系统已根据用户消息生成了结构化工单：\n"
    "{ticket_json}\n"
    "请基于该工单内容回复用户：先共情，再明确告知退货申请已被受理为工单、"
    "接下来会由售后专员跟进（如需提供购买凭证、订单号会另行说明），"
    "最后表达进一步协助的意愿。不要编造具体的退款金额、时限或物流信息。"
)


class TicketError(RuntimeError):
    """结构化工单生成失败——后续流程失去输入，属于必须显式暴露的硬性错误。"""


def load_api_key() -> str:
    """从环境变量 ZHIPUAI_API_KEY 读取 API Key，缺失时直接报配置错误。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱开放平台 API。\n"
            "请先在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取 Key，"
            "然后运行：ZHIPUAI_API_KEY=你的Key python3 main.py",
            file=sys.stderr,
        )
        sys.exit(2)
    return api_key


def chat_completion(
    api_key: str,
    messages: list,
    response_format: dict = None,
    reasoning_effort: str = "low",
) -> str:
    """调用 chat/completions 并返回 assistant 文本内容。

    API 层面的错误（鉴权失败、余额不足、限流等）在这里直接抛 RuntimeError，
    不做重试——这类错误是确定性的，重试只会掩盖问题。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        # 注意：不使用 tools/tool_choice。强制指定函数的 tool_choice 写法会被
        # 平台静默当成 auto，无法保证"必须先出工单"，故改由代码流程保证。
        "reasoning_effort": reasoning_effort,
    }
    if response_format is not None:
        # 仅支持 {"type": "json_object"}；json_schema 会被静默忽略，不可用。
        payload["response_format"] = response_format

    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code != 200:
        # 平台错误响应体形如 {"error": {"code": "...", "message": "..."}}
        try:
            error = resp.json().get("error", {})
            detail = "code={code}, message={message}".format(
                code=error.get("code"), message=error.get("message")
            )
        except ValueError:
            detail = resp.text[:500]
        raise RuntimeError(
            f"chat/completions 请求失败（HTTP {resp.status_code}）：{detail}"
        )

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"响应不是合法 JSON：{resp.text[:500]}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(
            "响应中没有 choices：" + json.dumps(data, ensure_ascii=False)[:500]
        )
    finish_reason = choices[0].get("finish_reason")
    if finish_reason != "stop":
        # sensitive / network_error / length 等异常结束，content 不可信
        raise RuntimeError(f"模型异常结束（finish_reason={finish_reason}）")

    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("模型返回的 content 为空")
    return content.strip()


def extract_json_object(text: str) -> dict:
    """从模型输出中提取 JSON 对象，容忍代码块围栏或前后杂文的格式偏差。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("输出中未找到 JSON 对象")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层不是对象")
    return obj


def validate_ticket(obj: dict) -> dict:
    """校验工单字段：category / summary 必须都是非空字符串。"""
    if not isinstance(obj, dict):
        raise ValueError("工单顶层必须是 JSON 对象")
    category = obj.get("category")
    summary = obj.get("summary")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("工单缺少字段 category（工单分类）或其为空")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("工单缺少字段 summary（问题摘要）或其为空")
    return {"category": category.strip(), "summary": summary.strip()}


def create_ticket(api_key: str, user_message: str) -> dict:
    """第 1 步（硬性）：生成结构化工单。

    无论模型意愿如何，这一步都会被无条件执行；输出解析/校验失败则重试，
    重试耗尽仍失败就抛 TicketError——后续流程拿不到输入，必须显式失败。
    """
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    failures = []
    for attempt in range(1, MAX_TICKET_ATTEMPTS + 1):
        try:
            content = chat_completion(
                api_key,
                messages,
                response_format={"type": "json_object"},
            )
            return validate_ticket(extract_json_object(content))
        except ValueError as exc:  # 含 json.JSONDecodeError；仅格式问题值得重试
            failures.append(f"第 {attempt} 次尝试输出不合法：{exc}")
            if attempt < MAX_TICKET_ATTEMPTS:
                time.sleep(1)
    raise TicketError(
        "结构化工单生成失败（共尝试 "
        f"{MAX_TICKET_ATTEMPTS} 次），后续流程缺少必要输入，流程终止：\n  "
        + "\n  ".join(failures)
    )


def compose_reply(api_key: str, user_message: str, ticket: dict) -> str:
    """第 2 步：基于工单内容给用户生成回复。

    ticket 是必填入参——没有工单就没有回复，调用方无法绕过第 1 步。
    """
    if not isinstance(ticket, dict) or not ticket.get("category") or not ticket.get("summary"):
        # 双保险：即使被误调用，也不允许在没有合法工单的情况下输出用户回复
        raise TicketError(f"非法工单，拒绝生成用户回复：{ticket!r}")
    system_prompt = REPLY_SYSTEM_PROMPT_TEMPLATE.format(
        ticket_json=json.dumps(ticket, ensure_ascii=False)
    )
    return chat_completion(
        api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )


def main() -> None:
    api_key = load_api_key()

    # ---- 第 1 步：结构化工单（硬性前置，失败即终止，绝不降级成纯安慰回复） ----
    print("[1/2] 正在生成结构化工单……")
    try:
        ticket = create_ticket(api_key, USER_MESSAGE)
    except TicketError as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        print(
            "未获得结构化工单，后续流程无法开始；不会向用户发送任何回复。",
            file=sys.stderr,
        )
        sys.exit(1)
    print("工单已生成（后续流程输入）：")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    # ---- 第 2 步：拿到工单之后，才允许生成给用户的回复 ----
    print("\n[2/2] 正在生成给用户的回复……")
    try:
        reply = compose_reply(api_key, USER_MESSAGE, ticket)
    except RuntimeError as exc:
        # 工单已产出并打印，仅回复生成失败：如实报错，不假装成功
        print(f"\n错误：工单已生成，但用户回复生成失败：{exc}", file=sys.stderr)
        sys.exit(1)
    print("给用户的回复：")
    print(reply)


if __name__ == "__main__":
    main()
