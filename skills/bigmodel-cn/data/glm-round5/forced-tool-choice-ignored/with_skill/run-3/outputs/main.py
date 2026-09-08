#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
客服工单处理脚本（智谱 AI 开放平台 / GLM）。

业务规则（硬性要求）：
    必须先产出一条结构化工单（字段：category 工单分类、summary 问题摘要），
    工单是后续流程的输入；校验通过后才生成给用户的回复。
    拿不到工单就明确报错退出，绝不退化成"只回一句安慰话"。

实现说明（为什么不用 Function Calling 强制出工单）：
    智谱 chat/completions 的 tool_choice 目前仅支持字符串 "auto"，
    OpenAI 风格的 {"type":"function","function":{"name":"..."}} 强制指定
    会被静默当成 auto 处理，模型完全可能跳过工具调用，无法保证工单一定产生。
    因此这里改为：在代码里无条件先发起一次 JSON 模式（response_format:
    {"type":"json_object"}）的独立请求生成工单，客户端 json.loads +
    字段校验（失败重试），通过后把工单作为上下文再请求模型生成回复。

运行方式：
    ZHIPUAI_API_KEY=你的Key python3 main.py
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
USER_MESSAGE = "我上周买的耳机坏了，想退货"

# glm-5.3 在标准端点强制开启思考（传 thinking.type=disabled 会报 1210），
# 分类/摘要属于轻量任务，用最低档 reasoning_effort 控制时延与开销。
REASONING_EFFORT = "low"

MAX_TICKET_ATTEMPTS = 3  # 工单抽取失败（非法 JSON / 字段缺失）时的总尝试次数
REQUEST_TIMEOUT = 120

# 工单分类受控词表（写入 prompt；返回不在词表内时仅告警，不判失败）
TICKET_CATEGORIES = ["退货退款", "商品质量", "物流配送", "售后咨询", "其他"]

TICKET_SYSTEM_PROMPT = (
    "你是客服工单系统的信息抽取模块。根据用户消息生成一条结构化工单，"
    "严格按以下 JSON 结构输出，只包含这两个字段，不要输出任何解释文字"
    "或代码块标记：\n"
    '{\n'
    '  "category": "<工单分类，只能从 '
    + "/".join(TICKET_CATEGORIES)
    + ' 中选一个>",\n'
    '  "summary": "<问题摘要，一句话概括用户的问题和诉求，不超过 50 字>"\n'
    '}'
)

REPLY_SYSTEM_PROMPT = (
    "你是一名电商平台的售后客服，语气友好、有同理心。"
    "系统已经为当前用户创建了工单，你会基于工单内容回复用户："
    "确认已收到问题并已建单、针对诉求给出下一步指引"
    "（如请用户提供订单号、描述故障情况以便安排退货）。"
    "不要编造具体政策细节（如退款到账时限、超出承诺的补偿），"
    "回复保持简洁，控制在 150 字以内。"
)


class ApiError(Exception):
    """调用 chat/completions 接口或解析响应结构失败。"""


def chat(api_key: str, messages: list, json_mode: bool = False) -> str:
    """调用 chat/completions，返回模型文本内容；失败抛 ApiError。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "reasoning_effort": REASONING_EFFORT,
        "max_tokens": 1024,
    }
    if json_mode:
        # 平台不支持 response_format.type=json_schema（会被静默忽略），
        # 只能用 json_object + 在 prompt 里写清结构，客户端自行校验。
        payload["response_format"] = {"type": "json_object"}
        payload["do_sample"] = False  # 贪心解码，让抽取结果更稳定
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
        raise ApiError(f"请求 chat/completions 失败：{exc}") from exc

    if resp.status_code != 200:
        # 智谱错误响应形如 {"error": {"code": "...", "message": "..."}}
        try:
            err = resp.json().get("error", {})
            detail = f"{err.get('code', '?')} {err.get('message', '')}".strip()
        except ValueError:
            detail = resp.text[:300]
        raise ApiError(f"API 返回 HTTP {resp.status_code}：{detail}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ApiError(f"响应中没有 choices：{json.dumps(data, ensure_ascii=False)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    if not content or not str(content).strip():
        raise ApiError(
            f"模型返回内容为空（finish_reason={choices[0].get('finish_reason')}）"
        )
    return str(content).strip()


def parse_ticket_json(raw: str) -> dict:
    """把模型输出解析为 dict；容忍 ```json 代码块包裹等常见噪声。"""
    text = raw.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 顶层不是对象：{type(obj).__name__}")
    return obj


def validate_ticket(obj: dict) -> dict:
    """校验工单必须字段；返回归一化后的 {category, summary}。"""
    category = obj.get("category")
    summary = obj.get("summary")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("字段 category 缺失或不是非空字符串")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("字段 summary 缺失或不是非空字符串")
    return {"category": category.strip(), "summary": summary.strip()}


def build_ticket(api_key: str) -> dict:
    """第一步（无条件执行）：生成并校验结构化工单。

    成功返回 {"category": ..., "summary": ...}；
    重试耗尽仍失败则返回 None，由调用方按业务规则终止流程。
    """
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": USER_MESSAGE},
    ]
    last_error = "未知错误"
    for attempt in range(1, MAX_TICKET_ATTEMPTS + 1):
        try:
            raw = chat(api_key, messages, json_mode=True)
            return validate_ticket(parse_ticket_json(raw))
        except (ApiError, ValueError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            print(
                f"[warn] 第 {attempt}/{MAX_TICKET_ATTEMPTS} 次工单抽取失败：{last_error}",
                file=sys.stderr,
            )
    print(f"[error] 工单抽取重试耗尽，最后一次错误：{last_error}", file=sys.stderr)
    return None


def compose_reply(api_key: str, ticket: dict) -> str:
    """第二步：以工单为上下文，生成给用户的回复。"""
    messages = [
        {"role": "system", "content": REPLY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"已创建的工单：{json.dumps(ticket, ensure_ascii=False)}\n"
                f"用户消息：{USER_MESSAGE}\n"
                "请回复该用户。"
            ),
        },
    ]
    return chat(api_key, messages)


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，"
            "请在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取后重试。",
            file=sys.stderr,
        )
        return 1

    # 硬性要求：先工单，后回复。工单拿不到就直接报错终止。
    ticket = build_ticket(api_key)
    if ticket is None:
        print(
            "错误：未能生成结构化工单（category/summary）。"
            "工单是后续流程的必要输入，按业务规则终止，本次不生成用户回复。",
            file=sys.stderr,
        )
        return 2

    if ticket["category"] not in TICKET_CATEGORIES:
        print(
            f"[warn] 工单分类 {ticket['category']!r} 不在受控词表内，"
            f"建议人工复核（词表：{'/'.join(TICKET_CATEGORIES)}）",
            file=sys.stderr,
        )

    print("=== 结构化工单（后续流程输入） ===")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    try:
        reply = compose_reply(api_key, ticket)
    except ApiError as exc:
        print(f"错误：工单已生成，但生成用户回复失败：{exc}", file=sys.stderr)
        return 3

    print("\n=== 给用户的回复 ===")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
