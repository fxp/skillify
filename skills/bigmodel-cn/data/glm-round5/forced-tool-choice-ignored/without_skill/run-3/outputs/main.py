# -*- coding: utf-8 -*-
"""客服工单处理脚本（智谱 GLM，仅依赖 requests）。

业务硬性要求——由代码强制保证，而不是寄希望于模型自觉：
  第一步：必须先产出结构化工单 {"category": 工单分类, "summary": 问题摘要}；
  第二步：工单校验通过后，才允许生成给用户的回复；
  拿不到合法工单就明确报错退出（exit code 1），
  绝不降级成"只回一句安慰话"就算处理完。

背景说明：智谱官方文档中 tool_choice 仅支持 "auto"（无法在协议层强制指定
某个函数），因此"必须先出工单"通过三层保障实现：
  1) 强约束的 system 提示词（只允许调用 create_ticket 工具）；
  2) 响应硬校验：必须有 tool_calls、函数名必须匹配、参数必须是合法 JSON
     且 category / summary 非空；
  3) 校验失败时把模型的错误行为记入上下文并纠正重试，仍失败则报错终止。

运行方式：
  ZHIPUAI_API_KEY=你的key python3 main.py
可选环境变量 ZHIPUAI_MODEL 覆盖默认模型（默认 glm-4.6）。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")
TIMEOUT = 60        # 单次请求超时（秒）
MAX_ATTEMPTS = 3    # 工单抽取最多尝试次数

USER_MESSAGE = "我上周买的耳机坏了，想退货"

CATEGORIES = ["退货退款", "商品质量", "物流配送", "售后维修", "使用咨询", "其他"]

TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": "为用户的客服请求创建一条结构化工单。这是回复用户之前必须完成的第一步。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": CATEGORIES,
                    "description": "工单分类",
                },
                "summary": {
                    "type": "string",
                    "description": "一句话问题摘要，客观概括用户的问题与诉求",
                },
            },
            "required": ["category", "summary"],
        },
    },
}

TICKET_SYSTEM_PROMPT = (
    "你是客服系统中的工单抽取模块，不是面向用户的客服。你的唯一职责是："
    "针对用户消息调用 create_ticket 工具，生成结构化工单。\n"
    "规则：\n"
    "1. 必须调用 create_ticket 工具，禁止直接用自然语言回复用户，"
    "禁止输出工具调用以外的任何内容；\n"
    "2. category 从给定分类中选最贴切的一个；\n"
    "3. summary 用一句话客观概括用户的问题与诉求，不要寒暄。"
)

NUDGE_MESSAGE = (
    "提醒：你刚才没有正确调用工具。请只调用 create_ticket 工具生成工单"
    "（参数：category、summary），不要输出任何自然语言。"
)


def _chat(api_key, messages, with_tools=False):
    """调用智谱对话补全接口，返回解析后的 JSON；任何异常统一抛 RuntimeError。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
    }
    if with_tools:
        # 官方文档：tool_choice 为 String，默认且仅支持 "auto"，
        # 不能在 API 层强制指定函数，因此配合提示词 + 响应硬校验保证工单产出。
        payload["tools"] = [TICKET_TOOL]
        payload["tool_choice"] = "auto"
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError("请求智谱 API 失败（网络错误或超时）：%s" % exc)
    if resp.status_code != 200:
        raise RuntimeError(
            "智谱 API 返回 HTTP %s：%s" % (resp.status_code, resp.text[:500])
        )
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError("智谱 API 返回了非 JSON 内容：%s" % resp.text[:500])
    if not data.get("choices"):
        raise RuntimeError(
            "智谱 API 未返回 choices，响应：%s"
            % json.dumps(data, ensure_ascii=False)[:500]
        )
    return data


def _parse_ticket(message):
    """从 assistant 消息中解析工单。

    成功返回 ({"category": ..., "summary": ...}, None)；
    失败返回 (None, 失败原因)，原因用于报错与纠正重试。
    """
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return None, "模型忽略了 create_ticket 工具，直接输出了文本"

    function = None
    for tool_call in tool_calls:
        candidate = (tool_call or {}).get("function") or {}
        if candidate.get("name") == "create_ticket":
            function = candidate
            break
    if function is None:
        names = [
            ((tc or {}).get("function") or {}).get("name") for tc in tool_calls
        ]
        return None, "模型调用了错误的工具：%r" % (names,)

    raw_args = function.get("arguments")
    try:
        # 官方文档：arguments 是 JSON 格式字符串，需要 json.loads 解析
        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except ValueError:
        return None, "工单参数不是合法 JSON：%r" % (raw_args,)
    if not isinstance(args, dict):
        return None, "工单参数不是 JSON 对象：%r" % (args,)

    ticket = {
        "category": str(args.get("category") or "").strip(),
        "summary": str(args.get("summary") or "").strip(),
    }
    missing = [key for key in ("category", "summary") if not ticket[key]]
    if missing:
        return None, "工单缺少必填字段：%s（原始参数：%s）" % (
            missing,
            json.dumps(args, ensure_ascii=False),
        )
    return ticket, None


def create_ticket(api_key):
    """第一步：先产出结构化工单。成功返回工单 dict；失败抛 RuntimeError。"""
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": USER_MESSAGE},
    ]
    last_reason = "未知原因"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        data = _chat(api_key, messages, with_tools=True)
        message = data["choices"][0].get("message") or {}
        ticket, reason = _parse_ticket(message)
        if ticket is not None:
            return ticket
        last_reason = reason
        # 把模型的错误行为记入上下文，追加纠正指令后重试
        content = str(message.get("content") or "").strip()
        if content:
            messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": NUDGE_MESSAGE})
    raise RuntimeError(
        "连续 %d 次调用均未产出合法工单，最后一次失败原因：%s。"
        "工单是后续流程的输入，没有工单就不能继续。" % (MAX_ATTEMPTS, last_reason)
    )


def generate_reply(api_key, ticket):
    """第二步：工单已校验通过，基于工单生成给用户的回复。"""
    system_prompt = (
        "你是一名电商平台的人工客服。系统已经为该用户登记了工单：\n"
        + json.dumps(ticket, ensure_ascii=False)
        + "\n请基于这份工单用中文回复用户：先共情确认问题，再告知工单已受理，"
        "最后给出退货的下一步指引（如提交退货申请、保留商品包装与配件、"
        "说明预计处理时效等）。语气诚恳具体，不要编造工单之外的政策细节。"
    )
    data = _chat(
        api_key,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": USER_MESSAGE},
        ],
    )
    reply = str((data["choices"][0].get("message") or {}).get("content") or "").strip()
    if not reply:
        raise RuntimeError("模型返回了空回复")
    return reply


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        print("用法：ZHIPUAI_API_KEY=你的key python3 main.py", file=sys.stderr)
        return 1

    # 第一步：结构化工单是硬性前置条件，拿不到就明确报错，绝不往下走
    try:
        ticket = create_ticket(api_key)
    except RuntimeError as exc:
        print(
            "[错误] 结构化工单未产出，流程在此终止，未生成任何用户回复：%s" % exc,
            file=sys.stderr,
        )
        return 1

    print("=" * 8, "第一步：结构化工单（后续流程的输入）", "=" * 8)
    print(json.dumps(ticket, ensure_ascii=False, indent=2))
    print()

    # 第二步：只有拿到工单之后，才生成给用户的回复
    try:
        reply = generate_reply(api_key, ticket)
    except RuntimeError as exc:
        print("[错误] 工单已产出，但生成用户回复失败：%s" % exc, file=sys.stderr)
        return 1

    print("=" * 8, "第二步：给用户的回复", "=" * 8)
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
