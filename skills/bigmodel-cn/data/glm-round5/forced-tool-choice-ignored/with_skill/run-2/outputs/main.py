#!/usr/bin/env python3
"""客服工单处理：必须先产出结构化工单（category/summary），再生成给用户的回复。

业务硬性约束：工单是后续流程的输入。拿不到合法工单就显式报错退出，
绝不退化为"只回一句安慰话"。

实现要点（对应 bigmodel.cn 平台的两个已知限制，见技能包 SKILL.md）：
1. tool_choice 仅支持 "auto"，OpenAI 风格强制指定单个函数的写法会被静默当成
   auto 处理，无法保证模型一定发起 create_ticket 工具调用；
2. response_format 不支持 {"type": "json_schema"}，只有 {"type": "json_object"}。
因此不在模型侧依赖"强制调用"，而是在代码侧无条件先完成工单这一步：
用 json_object 模式 + system prompt 写明字段结构，客户端 json.loads 解析、
字段校验、失败带反馈重试；工单合法后才把它作为上下文喂给第二次调用生成回复。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 标准端点文本旗舰模型，支持 response_format/json_object
USER_MESSAGE = "我上周买的耳机坏了，想退货"

HTTP_RETRIES = 3          # 429/5xx/网络错误的退避重试次数
HTTP_BACKOFF_SECONDS = 2  # 指数退避基数：2s、4s、8s
TICKET_JSON_RETRIES = 3   # 工单 JSON 解析/校验失败的纠正重试次数

TICKET_SYSTEM_PROMPT = (
    "你是电商客服的工单整理助手。请把用户消息整理成一条工单，"
    "严格只返回一个 JSON 对象，不要输出任何解释文字、注释或代码块。格式：\n"
    '{"category": "<工单分类，从：售后服务/退换货/商品质量/物流投诉/其他 中选一个>",'
    ' "summary": "<一句话问题摘要，30 字以内，须包含商品、问题、用户诉求>"}'
)


class TicketError(RuntimeError):
    """工单未能产出。业务上必须显式失败，不允许静默降级成普通回复。"""


def describe_http_error(resp):
    """把 HTTP 错误响应整理成可读信息，优先透出平台业务错误码。"""
    try:
        error = resp.json().get("error") or {}
        return f"HTTP {resp.status_code} code={error.get('code')} message={error.get('message')}"
    except ValueError:
        return f"HTTP {resp.status_code} {resp.text[:200]}"


def content_from_response(resp):
    """从 200 响应中取出 assistant 文本内容，结构异常时抛错。"""
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"响应不是合法 JSON：{exc}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应缺少 choices：{json.dumps(data, ensure_ascii=False)[:300]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content or not str(content).strip():
        raise RuntimeError(
            f"模型返回空内容（finish_reason={choices[0].get('finish_reason')}）"
        )
    return content


def chat(api_key, messages, extra_payload=None):
    """调用对话补全接口，返回 assistant 文本内容。

    429/5xx/网络错误按指数退避重试；401/403/400 等配置类错误重试无意义，直接抛出。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        # glm-5.3 在标准端点强制思考且不可关闭，用 low 档控制时延与开销
        "reasoning_effort": "low",
        "max_tokens": 2048,
    }
    if extra_payload:
        payload.update(extra_payload)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = "未知错误"
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_error = f"网络请求失败：{exc}"
        else:
            if resp.status_code < 400:
                return content_from_response(resp)
            detail = describe_http_error(resp)
            if resp.status_code != 429 and resp.status_code < 500:
                raise RuntimeError(f"API 调用失败（配置/参数类错误，不重试）：{detail}")
            last_error = detail
        if attempt < HTTP_RETRIES:
            time.sleep(HTTP_BACKOFF_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(f"API 调用重试 {HTTP_RETRIES} 次后仍失败：{last_error}")


def parse_ticket(content):
    """解析并校验工单 JSON，返回 (ticket, 失败原因)。合法时失败原因为 None。"""
    if not content or not content.strip():
        return None, "模型返回了空内容"
    text = content.strip()
    # 兜底：模型偶尔夹带解释文字或 ```json 代码块，截取首个 { 到最后一个 }
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"不是合法 JSON（{exc}）"
    if not isinstance(data, dict):
        return None, "JSON 顶层不是对象"
    ticket = {}
    for field in ("category", "summary"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"缺少有效字段 {field}"
        ticket[field] = value.strip()
    return ticket, None


def create_ticket(api_key, user_message):
    """第 1 步（硬性依赖）：产出结构化工单。失败重试，仍失败则抛 TicketError。"""
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    extra_payload = {
        # 平台仅支持 json_object，字段结构靠 system prompt 约束（无 json_schema 模式）
        "response_format": {"type": "json_object"},
        # 抽取任务要确定性输出：贪心解码，忽略采样参数
        "do_sample": False,
    }

    last_reason = "未发起请求"
    for _ in range(TICKET_JSON_RETRIES):
        content = chat(api_key, messages, extra_payload=extra_payload)
        ticket, reason = parse_ticket(content)
        if ticket is not None:
            return ticket
        last_reason = reason
        # 把坏输出作为反馈追加进对话，要求模型纠正后重试
        messages.append({"role": "assistant", "content": content or "(空响应)"})
        messages.append({
            "role": "user",
            "content": (
                f"你上一次的输出不合规：{reason}。"
                "请重新严格只返回一个符合要求格式的 JSON 对象，不要有任何其他文字。"
            ),
        })
    raise TicketError(f"重试 {TICKET_JSON_RETRIES} 次仍无法产出合法工单：{last_reason}")


def draft_reply(api_key, user_message, ticket):
    """第 2 步：工单已就绪，基于工单内容生成给用户的回复。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是电商客服。系统已在回复前生成结构化工单，你的回复必须与工单口径一致："
                "先安抚并确认用户的问题，再说明下一步处理方式（如退货申请如何受理）。"
                "语气友好，120 字以内，不要把工单 JSON 本身发给用户。工单内容：\n"
                + json.dumps(ticket, ensure_ascii=False)
            ),
        },
        {"role": "user", "content": user_message},
    ]
    return chat(api_key, messages)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用 API。", file=sys.stderr)
        return 1

    # 第 1 步：先拿工单；拿不到就显式报错，绝不给用户回复
    try:
        ticket = create_ticket(api_key, USER_MESSAGE)
    except (TicketError, RuntimeError) as exc:
        print(
            f"错误：工单生成失败，流程终止，未给用户回复。原因：{exc}",
            file=sys.stderr,
        )
        return 1

    print("=== 结构化工单（后续流程输入） ===")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))
    print()

    # 第 2 步：工单就绪后才生成回复
    try:
        reply = draft_reply(api_key, USER_MESSAGE, ticket)
    except RuntimeError as exc:
        print(f"错误：工单已生成，但回复生成失败。原因：{exc}", file=sys.stderr)
        return 1

    print("=== 给用户的回复 ===")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
