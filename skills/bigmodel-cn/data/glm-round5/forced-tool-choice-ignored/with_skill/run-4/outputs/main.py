#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客服工单处理脚本。

业务硬性要求：必须先产出一条结构化工单（category 工单分类 + summary 问题摘要），
然后才生成给用户的回复；工单是后续流程的输入，拿不到工单就显式报错退出，
绝不允许退化成"只回一句安慰话就算处理完了"。

实现说明（为什么不用 Function Calling 强制调用建工单）：
智谱开放平台 chat/completions 的 tool_choice 目前仅支持字符串 "auto"，
传 {"type":"function","function":{"name":"create_ticket"}} 这种强制指定写法
不会报错，但会被静默当成 auto 处理——模型完全可能跳过工具调用直接回答，
上面的硬性约束就形同虚设。response_format 同样不支持 json_schema（会被静默忽略），
只有 text / json_object 两种。因此本脚本把"必须先建工单"落实为代码里的调用顺序，
而不是依赖模型的工具调用意愿：

  第 1 步  无条件先发起第一次请求，response_format={"type":"json_object"}
          + prompt 中写明目标字段结构，让模型产出工单 JSON；
  第 2 步  客户端做 json.loads + 字段校验（category/summary 必须是非空字符串），
          解析或校验失败自动重试，重试耗尽仍失败则报错退出、不进入回复环节；
  第 3 步  只有工单校验通过后，才发起第二次请求生成用户回复，
          并把工单内容作为上下文喂给模型。

运行方式：ZHIPUAI_API_KEY 环境变量提供 Key，直接 python3 main.py。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 纯文本旗舰模型，支持 response_format=json_object
TICKET_MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = 60  # 秒

USER_MESSAGE = "我上周买的耳机坏了，想退货"

TICKET_SYSTEM_PROMPT = (
    "你是客服工单系统的信息抽取模块。请根据用户消息生成一条结构化工单，"
    "只输出一个 JSON 对象，不要输出任何解释文字、markdown 代码块或多余标点。"
    "JSON 必须恰好包含两个字段：\n"
    '{"category": "<工单分类>", "summary": "<问题摘要>"}\n'
    "字段要求：\n"
    "- category：从以下分类中选最贴切的一个："
    "退货退款、商品质量、物流配送、售后维修、账号问题、其他。\n"
    "- summary：一句话概括用户的问题和诉求，不超过 50 字，"
    "必须保留关键事实（商品、故障情况、诉求）。"
)

REPLY_SYSTEM_PROMPT = (
    "你是电商平台的客服助手。系统已经为当前用户生成了结构化工单，"
    "请基于工单内容，用友好、专业的语气回复用户："
    "确认已收到并记录其问题，说明下一步处理安排（如退货流程会由专人跟进），"
    "并安抚用户情绪。回复保持简洁，3 句以内。"
)


class ApiError(RuntimeError):
    """调用智谱 API 失败（网络异常 / HTTP 非 200 / 响应结构异常）。"""


class TicketGenerationError(RuntimeError):
    """工单生成失败。业务上属于致命错误：没有工单就不能给用户回复。"""


def chat(api_key, messages, response_format=None, extra=None):
    """调用对话补全接口，返回 assistant 的文本内容。

    出现任何网络 / HTTP / 结构问题都抛 ApiError，由调用方决定重试或终止。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "response_format": response_format or {"type": "text"},
    }
    if extra:
        payload.update(extra)
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
        raise ApiError(f"请求 chat/completions 网络异常：{exc}") from exc
    if resp.status_code != 200:
        # 带出平台错误码/信息便于排查（如 1113 余额不足、1210 参数非法）
        raise ApiError(
            f"调用 chat/completions 失败：HTTP {resp.status_code}，响应：{resp.text[:500]}"
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"响应不是合法 JSON：{resp.text[:500]}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise ApiError(f"响应中没有 choices：{json.dumps(data, ensure_ascii=False)[:500]}")
    content = (choices[0].get("message") or {}).get("content")
    if not content or not str(content).strip():
        raise ApiError(f"模型返回内容为空：{json.dumps(data, ensure_ascii=False)[:500]}")
    return str(content).strip()


def parse_ticket_json(text):
    """把模型输出解析成 dict。

    json_object 模式下通常是干净的 JSON，但模型仍可能夹带解释文字或代码块，
    所以先直接 json.loads，失败再退化到截取最外层 {...} 子串重试。
    """
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass
    raise ValueError(f"无法解析为 JSON：{text[:200]}")


def validate_ticket(obj):
    """校验工单结构：必须是 dict，且 category / summary 均为非空字符串。"""
    if not isinstance(obj, dict):
        raise ValueError(f"工单不是 JSON 对象：{obj!r}")
    ticket = {}
    for field in ("category", "summary"):
        value = obj.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"工单缺少合法的 {field} 字段：{obj!r}")
        ticket[field] = value.strip()
    return ticket


def create_ticket(api_key, user_message):
    """第 1 步：生成结构化工单。成功返回 {"category": ..., "summary": ...}。

    重试耗尽仍拿不到合法工单时抛 TicketGenerationError——
    这是硬性业务约束的守门函数，失败绝不返回兜底文案。
    """
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    last_error = None
    for attempt in range(1, TICKET_MAX_ATTEMPTS + 1):
        try:
            raw = chat(
                api_key,
                messages,
                response_format={"type": "json_object"},  # 平台仅支持 text/json_object
                # glm-5.3 在标准端点强制思考且无法关闭，抽取类简单任务用 low 档降低时延
                extra={"do_sample": False, "reasoning_effort": "low"},
            )
            return validate_ticket(parse_ticket_json(raw))
        except (ApiError, ValueError) as exc:
            last_error = exc
            print(
                f"[warn] 第 {attempt}/{TICKET_MAX_ATTEMPTS} 次生成工单失败：{exc}",
                file=sys.stderr,
            )
    raise TicketGenerationError(
        f"重试 {TICKET_MAX_ATTEMPTS} 次仍无法产出合法工单（category/summary），"
        f"按硬性要求终止流程、不生成用户回复。最后一次错误：{last_error}"
    )


def draft_reply(api_key, user_message, ticket):
    """第 2 步（仅在工单成功后执行）：基于工单上下文生成给用户的回复。"""
    messages = [
        {"role": "system", "content": REPLY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "已生成的结构化工单：\n"
                f"{json.dumps(ticket, ensure_ascii=False)}\n\n"
                f"用户消息：{user_message}\n\n"
                "请回复用户。"
            ),
        },
    ]
    return chat(api_key, messages)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        return 1

    print(f"用户消息：{USER_MESSAGE}\n")

    # 硬性顺序约束：先工单，后回复；工单失败直接终止，不进入回复环节
    try:
        ticket = create_ticket(api_key, USER_MESSAGE)
    except TicketGenerationError as exc:
        print(f"错误：工单生成失败，流程终止（未给用户回复）。\n{exc}", file=sys.stderr)
        return 1
    print("已生成工单（后续流程输入）：")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    try:
        reply = draft_reply(api_key, USER_MESSAGE, ticket)
    except ApiError as exc:
        print(f"错误：工单已生成，但生成用户回复失败。\n{exc}", file=sys.stderr)
        return 1
    print("\n给用户的回复：")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
