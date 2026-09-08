#!/usr/bin/env python3
"""客服工单处理脚本（智谱 AI 开放平台）。

业务流程（硬性要求，不可绕过）：
  1. 必须先从用户消息中产出一条结构化工单，字段固定两个：
     - category：工单分类
     - summary：问题摘要
  2. 工单通过校验后，才允许生成给用户的回复；
  3. 任一环节拿不到合法工单，立即明确报错并以非零退出码退出，
     绝不输出"只安抚、不建单"的回复。

接口说明（来自官方文档 https://docs.bigmodel.cn ）：
  - 请求地址：POST https://open.bigmodel.cn/api/paas/v4/chat/completions
  - 认证方式：Authorization: Bearer <API Key>
  - 重要：智谱 API 的 tool_choice 默认且仅支持 "auto"，
    不支持强制指定具体函数（不同于 OpenAI 的 {"type":"function",...} 写法）。
    因此不能假设"传了 tools 模型就一定调用"，本脚本的做法是：
      a) 用严格的 system 提示词要求模型必须调用 create_ticket；
      b) 对返回做强校验，模型没调用就视为失败；
      c) 工具调用被忽略时，降级用 response_format=json_object 再抽取一次；
      d) 两条路径都失败 -> 明确报错退出，不生成任何用户回复。

依赖：仅 requests（其余均为标准库）。
运行：ZHIPUAI_API_KEY=你的Key python3 main.py
      （可选环境变量 ZHIPUAI_MODEL 指定模型，默认 glm-5.3）
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3")
TIMEOUT_SECONDS = 60

USER_MESSAGE = "我上周买的耳机坏了，想退货"

# 第一步（结构化工单）的工具定义：function calling schema
TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": "为用户诉求创建一条结构化客服工单。必须在回复用户之前调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "工单分类，从这些里选一个：售后退换/物流查询/账号问题/产品咨询/投诉/其他",
                },
                "summary": {
                    "type": "string",
                    "description": "问题摘要，用一句话概括用户的诉求和关键事实",
                },
            },
            "required": ["category", "summary"],
        },
    },
}

TICKET_TOOL_SYSTEM_PROMPT = (
    "你是客服工单系统的工单抽取器。你的唯一任务是调用 create_ticket 函数，"
    "根据用户消息产出结构化工单（category=工单分类，summary=一句话问题摘要）。\n"
    "必须调用该函数，禁止直接回复用户，禁止输出任何解释性文字。"
)

TICKET_JSON_SYSTEM_PROMPT = (
    "你是客服工单系统的工单抽取器。请根据用户消息抽取一条工单，"
    "只输出一个 JSON 对象，不要输出任何其他文本，格式为："
    '{"category": "<工单分类>", "summary": "<问题摘要>"}\n'
    "category 从这些分类中选一个：售后退换/物流查询/账号问题/产品咨询/投诉/其他。"
)

REPLY_SYSTEM_PROMPT = (
    "你是电商平台的客服助理。系统已经成功创建了工单（见用户消息中附带的工单内容），"
    "请基于工单内容，用中文给用户写一段简短、真诚、有同理心的回复："
    "确认收到其诉求、说明工单已登记并进入处理流程、告知后续会有专人跟进。\n"
    "注意：不要承诺具体退款金额或处理时限，不要编造物流单号等事实。"
)


class TicketError(RuntimeError):
    """工单生成或校验失败——业务硬性要求未满足，流程必须终止。"""


def chat_completion(api_key, messages, *, tools=None, response_format=None, temperature=0.1):
    """调用智谱 chat/completions，返回 choices[0].message（dict）。

    网络/HTTP/响应结构层面的错误统一抛 RuntimeError，附带可读信息。
    """
    payload = {"model": MODEL, "messages": messages, "temperature": temperature}
    if tools is not None:
        payload["tools"] = tools
        # 智谱 API 的 tool_choice 默认且仅支持 "auto"，无法强制指定函数，
        # 这里显式传 "auto" 以明确策略；模型是否调用靠提示词约束 + 下游强校验兜底。
        payload["tool_choice"] = "auto"
    if response_format is not None:
        payload["response_format"] = response_format

    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"调用智谱 API 失败（网络错误）：{exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"调用智谱 API 失败：HTTP {resp.status_code}，响应片段：{resp.text[:500]}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"调用智谱 API 失败：响应不是合法 JSON：{resp.text[:500]}") from exc

    choices = data.get("choices") or []
    if not choices or not choices[0].get("message"):
        raise RuntimeError(
            f"调用智谱 API 失败：响应中没有 choices[0].message：{json.dumps(data, ensure_ascii=False)[:500]}"
        )
    return choices[0]["message"]


def extract_ticket_with_tool(api_key):
    """优先路径：function calling 抽取工单。

    返回工具参数解析出的 dict；若模型忽略工具、直接回了文本，返回 None
    （这正是 tool_choice 无法强制指定时已知的失败模式，由调用方降级处理）。
    """
    message = chat_completion(
        api_key,
        [
            {"role": "system", "content": TICKET_TOOL_SYSTEM_PROMPT},
            {"role": "user", "content": USER_MESSAGE},
        ],
        tools=[TICKET_TOOL],
    )
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") != TICKET_TOOL["function"]["name"]:
            continue
        raw_arguments = function.get("arguments") or ""
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise TicketError(
                f"模型调用了 create_ticket，但 arguments 不是合法 JSON：{exc}；原始内容：{raw_arguments[:200]}"
            ) from exc
        return arguments
    return None


def extract_ticket_with_json_mode(api_key):
    """降级路径：response_format=json_object 抽取工单。解析失败返回 None。"""
    message = chat_completion(
        api_key,
        [
            {"role": "system", "content": TICKET_JSON_SYSTEM_PROMPT},
            {"role": "user", "content": USER_MESSAGE},
        ],
        response_format={"type": "json_object"},
    )
    content = (message.get("content") or "").strip()
    if not content:
        return None
    # 防御：模型偶尔会把 JSON 包在 ```json ... ``` 代码块里，先剥掉围栏
    if content.startswith("```"):
        content = content.strip("` \n")
        if content[:4].lower() == "json":
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def validate_ticket(ticket):
    """校验并归一化工单：必须是含非空 category、summary 两个字段的对象。

    任一字段缺失或为空都抛 TicketError——这是"拿到工单"的判定标准。
    """
    if not isinstance(ticket, dict):
        raise TicketError(
            f"工单格式错误：应为 JSON 对象，实际是 {type(ticket).__name__}；原始内容：{ticket!r}"
        )
    normalized = {}
    for field in ("category", "summary"):
        value = ticket.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TicketError(
                f"工单字段缺失或为空：{field!r}；原始内容：{json.dumps(ticket, ensure_ascii=False)}"
            )
        normalized[field] = value.strip()
    return normalized


def generate_reply(api_key, ticket):
    """第二步：在工单已产出并校验通过之后，生成给用户的回复。"""
    message = chat_completion(
        api_key,
        [
            {"role": "system", "content": REPLY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户消息：{USER_MESSAGE}\n\n"
                    f"已创建的工单：{json.dumps(ticket, ensure_ascii=False)}\n\n"
                    "请给用户写回复。"
                ),
            },
        ],
        temperature=0.3,
    )
    reply = (message.get("content") or "").strip()
    if not reply:
        raise RuntimeError("生成用户回复失败：模型返回内容为空")
    return reply


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise TicketError("环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用智谱 API")

    # ── 第一步：产出结构化工单（硬性前置条件，拿不到就必须报错）──
    ticket_raw = extract_ticket_with_tool(api_key)
    if ticket_raw is None:
        print(
            "[警告] 模型未调用 create_ticket 工具（智谱 API 的 tool_choice 仅支持 auto，无法强制），"
            "降级为 JSON 模式重新抽取工单",
            file=sys.stderr,
        )
        ticket_raw = extract_ticket_with_json_mode(api_key)
    if ticket_raw is None:
        raise TicketError(
            "无法生成结构化工单：模型既未调用 create_ticket 工具，"
            "JSON 模式也未返回合法 JSON。流程终止，不向用户发送任何回复。"
        )

    ticket = validate_ticket(ticket_raw)  # 字段不合法会抛 TicketError 并终止

    # ── 第二步：工单落档（打印出来，作为后续流程的输入）──
    print("=== 结构化工单 ===")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))

    # ── 第三步：只有拿到合法工单之后，才生成给用户的回复 ──
    reply = generate_reply(api_key, ticket)
    print("=== 给用户的回复 ===")
    print(reply)


if __name__ == "__main__":
    try:
        main()
    except TicketError as exc:
        print(f"[工单错误] {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
