#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客服工单处理脚本（智谱 GLM，仅依赖 requests）。

业务硬性要求：必须先产出一条结构化工单（category / summary）作为后续流程的输入，
然后才允许给用户回复。拿不到工单就显式报错退出，不允许只回一句安慰话。

实现说明（为什么不能只靠 tool_choice 强制）：
智谱官方文档注明 tool_choice「默认且仅支持 auto」，强制指定函数的写法
（如 {"type": "function", "function": {"name": ...}}）可能被服务端忽略。
因此顺序保证由代码完成：
  1. 第一步只挂 create_ticket 工具，要求模型必须调用；
  2. 对返回做硬校验（tool_calls 存在、字段齐全且非空），不合规则纠错重试；
  3. 重试耗尽仍无工单 -> 抛异常、非零退出，绝不进入第二步；
  4. 工单落定后才发起第二次调用生成用户回复（该次不挂任何工具）。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3")
MAX_ATTEMPTS = 3
TIMEOUT = 60

USER_MESSAGE = "我上周买的耳机坏了，想退货"

CREATE_TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": "为用户诉求创建一条结构化客服工单。必须在回复用户之前调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "工单分类",
                    "enum": ["退货退款", "换货维修", "质量问题", "物流配送", "其他"],
                },
                "summary": {
                    "type": "string",
                    "description": "问题摘要：一句话中文概括用户的问题与诉求，不超过 50 字",
                },
            },
            "required": ["category", "summary"],
        },
    },
}

TICKET_SYSTEM_PROMPT = (
    "你是客服系统的工单生成器。无论用户说什么，本轮你的唯一任务就是立即调用 "
    "create_ticket 工具：category 从枚举中选择最匹配的一项，summary 一句话概括问题与诉求。"
    "禁止输出任何自然语言文字，禁止跳过工具调用。"
)

REPLY_SYSTEM_PROMPT = (
    "你是电商平台的客服助手。系统已经为当前用户创建了工单（见下方 JSON）。"
    "请基于工单内容，用中文给用户一段简短、友好、可执行的回复："
    "确认受理、安抚情绪，并给出耳机退货的下一步指引（如在订单页申请售后、保留包装配件）。"
    "工单 JSON：{ticket_json}"
)


class TicketUnavailableError(RuntimeError):
    """模型始终没有产出合规的结构化工单。"""


def _chat(api_key: str, payload: dict) -> dict:
    """调用 chat completions，网络 / HTTP / 业务错误统一转成 RuntimeError。"""
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"请求智谱 API 失败：{exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"智谱 API 返回 HTTP {resp.status_code}：{resp.text[:500]}"
        )

    try:
        data = resp.json()
        message = data["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"智谱 API 响应格式异常：{resp.text[:500]}") from exc
    return message


def _extract_ticket(message: dict):
    """从模型消息里解析 create_ticket 的工具调用参数，字段不全返回 None。"""
    for tool_call in message.get("tool_calls") or []:
        function = (tool_call or {}).get("function") or {}
        if function.get("name") != "create_ticket":
            continue
        raw_args = function.get("arguments")
        # 官方文档：arguments 是 JSON 格式字符串；个别兼容端会直接给对象，两者都兼容
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                continue
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            continue
        if not isinstance(args, dict):
            continue
        category = str(args.get("category") or "").strip()
        summary = str(args.get("summary") or "").strip()
        if category and summary:
            return {"category": category, "summary": summary}
    return None


def create_ticket(api_key: str) -> dict:
    """第一步：产出结构化工单。失败重试，重试耗尽抛 TicketUnavailableError。"""
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": USER_MESSAGE},
    ]
    for _ in range(MAX_ATTEMPTS):
        message = _chat(
            api_key,
            {
                "model": MODEL,
                "messages": messages,
                "tools": [CREATE_TICKET_TOOL],
                # 文档注明仅稳定支持 "auto"；强制指定可能被忽略，
                # 顺序保证靠上面的提示词约束和 _extract_ticket 的硬校验兜底
                "tool_choice": "auto",
                "temperature": 0.1,
            },
        )
        ticket = _extract_ticket(message)
        if ticket:
            return ticket
        # 模型忽略了工具调用要求（forced tool choice 被忽略的典型表现），纠错后重试
        messages.append(
            {"role": "assistant", "content": message.get("content") or ""}
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "你刚才没有调用 create_ticket 工具，这不符合要求。"
                    "请立刻调用 create_ticket 工具生成工单，除此之外不要输出任何内容。"
                ),
            }
        )
    raise TicketUnavailableError(
        f"连续 {MAX_ATTEMPTS} 次尝试均未通过 create_ticket 工具获得结构化工单"
    )


def reply_to_user(api_key: str, ticket: dict) -> str:
    """第二步：工单已落定，生成给用户的回复。本次调用不挂任何工具。"""
    message = _chat(
        api_key,
        {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": REPLY_SYSTEM_PROMPT.format(
                        ticket_json=json.dumps(ticket, ensure_ascii=False)
                    ),
                },
                {"role": "user", "content": USER_MESSAGE},
            ],
            "temperature": 0.5,
        },
    )
    reply = str(message.get("content") or "").strip()
    if not reply:
        raise RuntimeError("模型返回了空的用户回复")
    return reply


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未配置 API Key，请先设置环境变量 ZHIPUAI_API_KEY。",
            file=sys.stderr,
        )
        return 1

    # 第一步：工单是硬性前置条件，失败即终止，不进入回复环节
    try:
        ticket = create_ticket(api_key)
    except (RuntimeError, TicketUnavailableError) as exc:
        print(
            f"错误：无法生成结构化工单，用户回复流程已终止（后续流程没有输入）：{exc}",
            file=sys.stderr,
        )
        return 1

    print("【第 1 步 · 结构化工单（后续流程输入）】")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    # 第二步：有了工单才生成回复
    try:
        reply = reply_to_user(api_key, ticket)
    except RuntimeError as exc:
        print(f"错误：工单已生成，但生成用户回复失败：{exc}", file=sys.stderr)
        return 1

    print("\n【第 2 步 · 给用户的回复】")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
