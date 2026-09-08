#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客服工单处理：必须先产出结构化工单（category + summary），再回复用户。

业务硬性约束：工单是后续流程的输入。拿不到工单就显式报错退出，
绝不退化为"只回一句安慰话"。

实现说明：智谱对话补全接口的 tool_choice 目前仅支持 "auto"（不支持
"required"，也不支持指定函数的对象形式），所以"必须先调工具"无法下推给
服务端强制。本脚本在客户端兜底：强约束写进 system 提示，收到响应后校验
是否真的发起了 create_ticket 调用且两个字段齐全；模型若直接回了文本则
纠正重试，重试耗尽仍拿不到工单就报错终止，不生成任何用户回复。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
USER_MESSAGE = "我上周买的耳机坏了，想退货"

MAX_TICKET_ATTEMPTS = 3  # 工单生成的最大尝试轮数
REQUEST_TIMEOUT = 60     # 单次请求超时（秒）


class TicketError(RuntimeError):
    """无法产出结构化工单——下游流程没有输入，必须显式失败。"""


TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": (
            "创建一条结构化客服工单。处理任何用户消息前必须先调用本工具；"
            "在拿到工单结果之前，禁止用自然语言直接回复或安抚用户。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "工单分类，例如：售后退货、产品质量、物流配送、使用咨询、其他",
                },
                "summary": {
                    "type": "string",
                    "description": "用户问题的一句话摘要，需覆盖关键信息（商品、问题、诉求）",
                },
            },
            "required": ["category", "summary"],
        },
    },
}


def call_glm(messages, tools=None):
    """调用智谱对话补全接口，返回首条 choices 的 message。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise TicketError("环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API")

    payload = {"model": MODEL, "messages": messages, "temperature": 0.2}
    if tools:
        payload["tools"] = tools
        # 文档明确 tool_choice 仅支持 "auto"，无法在服务端强制指定工具，
        # "先出工单"的约束由本脚本的响应校验来兜底。
        payload["tool_choice"] = "auto"

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TicketError("请求智谱 API 失败：%s" % exc) from exc

    if resp.status_code != 200:
        raise TicketError(
            "智谱 API 返回 HTTP %d：%s" % (resp.status_code, resp.text[:500])
        )

    data = resp.json()
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        detail = json.dumps(data, ensure_ascii=False)[:500]
        raise TicketError("智谱 API 响应缺少 choices[0].message：%s" % detail) from exc


def find_ticket_call(message):
    """在模型消息的 tool_calls 里找 create_ticket 调用，找不到返回 None。"""
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        if function.get("name") == "create_ticket":
            return tool_call
    return None


def parse_ticket_args(tool_call):
    """解析工具调用参数。arguments 是 JSON 字符串；字段缺失/为空返回 None。"""
    function = tool_call.get("function") or {}
    try:
        args = json.loads(function.get("arguments") or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(args, dict):
        return None
    category = str(args.get("category") or "").strip()
    summary = str(args.get("summary") or "").strip()
    if category and summary:
        return {"category": category, "summary": summary}
    return None


def create_ticket():
    """第一阶段：强制先拿到结构化工单。

    返回 (ticket, tool_call_id, messages)；messages 已包含带 tool_calls 的
    assistant 消息，供第二阶段继续对话。
    """
    messages = [
        {
            "role": "system",
            "content": (
                "你是客服工单系统的预处理模块。规则：对任何用户消息，必须首先调用 "
                "create_ticket 工具生成结构化工单（category 与 summary 均不能为空），"
                "在工具返回结果之前不允许用自然语言回答、安抚或反问用户。"
            ),
        },
        {"role": "user", "content": USER_MESSAGE},
    ]

    last_reply = ""
    for _ in range(MAX_TICKET_ATTEMPTS):
        message = call_glm(messages, tools=[TICKET_TOOL])
        tool_call = find_ticket_call(message)
        ticket = parse_ticket_args(tool_call) if tool_call else None
        if ticket is not None:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls"),
                }
            )
            return ticket, tool_call.get("id"), messages

        # 走到这里说明模型忽略了"先出工单"的约束直接回了文本（tool_choice 只有
        # auto，服务端拦不住）。把跑偏的输出记入上下文，再明确纠正一轮。
        last_reply = (message.get("content") or "").strip()
        messages.append(
            {"role": "assistant", "content": last_reply or "（模型未按要求输出）"}
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "你的上一条回复不符合要求：没有调用 create_ticket 就直接回了话。"
                    "工单是后续流程的硬性输入，请立即调用 create_ticket 工具，"
                    "参数必须包含非空的 category 和 summary，除此之外不要输出任何文字。"
                ),
            }
        )

    raise TicketError(
        "连续 %d 轮未能生成结构化工单（模型始终没有调用 create_ticket，"
        "或字段为空），后续流程缺少输入，流程终止、不生成用户回复。"
        "模型最后一次输出：%r" % (MAX_TICKET_ATTEMPTS, last_reply[:200])
    )


def generate_reply(ticket, tool_call_id, messages):
    """第二阶段：工单已生成，回传工具结果并生成面向用户的最终回复。"""
    ticket_id = "TK-%d" % int(time.time() * 1000)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(
                {"ticket_id": ticket_id, "status": "created", **ticket},
                ensure_ascii=False,
            ),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "工单已创建成功。现在请直接回复用户：确认其遇到的问题、"
                "说明退货流程与下一步操作。不要再调用任何工具。"
            ),
        }
    )

    # 不传 tools，模型只能输出文本回复。
    message = call_glm(messages, tools=None)
    reply = (message.get("content") or "").strip()
    if not reply:
        raise RuntimeError("工单已生成，但模型未返回给用户的回复文本")
    return ticket_id, reply


def main():
    # 第一阶段：先拿工单，拿不到就明确报错，绝不往下走。
    try:
        ticket, tool_call_id, messages = create_ticket()
    except TicketError as exc:
        print("[错误] 工单生成失败：%s" % exc, file=sys.stderr)
        print(
            "按业务要求，未取得结构化工单前不得回复用户，流程已终止。",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=== 结构化工单（后续流程输入）===")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    # 第二阶段：基于工单生成用户回复。
    try:
        ticket_id, reply = generate_reply(ticket, tool_call_id, messages)
    except RuntimeError as exc:
        print("[错误] 用户回复生成失败：%s" % exc, file=sys.stderr)
        sys.exit(1)

    print("=== 给用户的回复（工单号 %s）===" % ticket_id)
    print(reply)


if __name__ == "__main__":
    main()
