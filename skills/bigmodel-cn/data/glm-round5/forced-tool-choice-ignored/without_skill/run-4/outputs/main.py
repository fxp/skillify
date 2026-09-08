"""客服工单处理脚本。

业务规则（硬性要求）：
1. 必须先产出一条结构化工单（字段：category 工单分类、summary 问题摘要），
   工单是后续流程的输入；
2. 只有拿到合法工单之后，才允许生成给用户的回复；
3. 拿不到工单就必须明确报错退出，绝不能只用一句安慰话充当处理结果。

实现说明：
- 智谱开放平台 https://open.bigmodel.cn/api/paas/v4/chat/completions 的
  tool_choice 参数当前仅支持 "auto"（无法在 API 层强制指定函数），
  因此脚本在客户端做严格校验：模型未按约定调用 create_ticket、
  或参数缺字段/不是合法 JSON 时，重试若干次后直接报错，不会进入回复步骤。
- 仅依赖 requests，API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 模型可用环境变量 ZHIPUAI_MODEL 覆盖
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")
TIMEOUT = 60
# 工单提取最多尝试次数（tool_choice 无法强制，模型偶尔不调用工具时重试）
MAX_ATTEMPTS = 3

USER_MESSAGE = "我上周买的耳机坏了，想退货"

# 工单工具定义：让模型以函数调用的形式产出结构化工单
TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": "创建客服工单。在给用户任何回复之前，必须先调用本函数登记工单。",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "工单分类，例如：退货退款、产品质量、物流配送、售后咨询等",
                },
                "summary": {
                    "type": "string",
                    "description": "问题摘要，一句话概括用户的问题与诉求",
                },
            },
            "required": ["category", "summary"],
        },
    },
}


def _chat(api_key: str, payload: dict) -> dict:
    """调用对话补全接口，返回解析后的 JSON；网络/HTTP/格式错误统一抛异常。"""
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def _validate_ticket(data: object) -> dict:
    """校验候选工单：必须是包含非空 category/summary 的对象，返回规范化工单。"""
    if not isinstance(data, dict):
        raise ValueError("工单不是 JSON 对象")
    category = data.get("category")
    summary = data.get("summary")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("工单缺少非空字段 category")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("工单缺少非空字段 summary")
    return {"category": category.strip(), "summary": summary.strip()}


def _ticket_from_tool_calls(message: dict):
    """从 assistant 消息的 tool_calls 里解析 create_ticket 的参数，失败返回 None。"""
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        if function.get("name") != "create_ticket":
            continue
        try:
            arguments = json.loads(function.get("arguments") or "")
        except json.JSONDecodeError:
            return None
        try:
            return _validate_ticket(arguments)
        except ValueError:
            return None
    return None


def _ticket_from_content(message: dict):
    """兜底：个别时候模型不触发 tool_calls 而把 JSON 写进 content，尝试解析。"""
    content = message.get("content")
    if not isinstance(content, str) or "{" not in content:
        return None
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        return _validate_ticket(json.loads(match.group(0)))
    except (json.JSONDecodeError, ValueError):
        return None


def create_ticket(api_key: str) -> dict:
    """步骤 1：产出结构化工单。拿不到合法工单时抛异常，绝不返回 None 混过去。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是客服系统的工单预处理模块，唯一任务是分析用户消息并调用 "
                    "create_ticket 函数生成结构化工单（category、summary 两个字段都必须有内容）。"
                    "禁止直接回答或安慰用户，禁止输出函数调用以外的任何正文。"
                    "注意：平台 tool_choice 仅支持 auto，请务必主动调用 create_ticket。"
                ),
            },
            {"role": "user", "content": USER_MESSAGE},
        ],
        "tools": [TICKET_TOOL],
        # 平台当前仅支持 "auto"，无法在 API 层强制调用，故靠提示词 + 客户端校验兜底
        "tool_choice": "auto",
        "temperature": 0.1,
    }

    last_reason = "未知原因"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = _chat(api_key, payload)
        choices = result.get("choices") or []
        message = choices[0].get("message") if choices else None
        if not isinstance(message, dict):
            last_reason = f"响应结构异常: {json.dumps(result, ensure_ascii=False)[:300]}"
        else:
            ticket = _ticket_from_tool_calls(message)
            if ticket is not None:
                return ticket
            ticket = _ticket_from_content(message)
            if ticket is not None:
                print(
                    f"[警告] 第 {attempt} 次尝试未触发 tool_calls，已从 content 兜底解析出工单",
                    file=sys.stderr,
                )
                return ticket
            last_reason = (
                f"模型未按要求调用 create_ticket，message="
                f"{json.dumps(message, ensure_ascii=False)[:300]}"
            )
        print(f"[警告] 第 {attempt}/{MAX_ATTEMPTS} 次尝试未获得合法工单: {last_reason}",
              file=sys.stderr)

    raise RuntimeError(
        "未能生成结构化工单（category/summary），按业务规则中止流程，不生成用户回复。"
        f"最后失败原因: {last_reason}"
    )


def generate_reply(api_key: str, ticket: dict) -> str:
    """步骤 2：工单已确认后，基于工单内容生成给用户的回复。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是亲切的客服助手。系统已经为该用户创建了工单，"
                    "请基于工单内容用中文给用户一段简短温暖的回复：确认问题已受理、"
                    "退货申请已登记，并请用户留意后续处理。不要编造具体时限或政策细节。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户消息：{USER_MESSAGE}\n\n"
                    f"已创建工单：{json.dumps(ticket, ensure_ascii=False)}\n\n"
                    "请给用户回复。"
                ),
            },
        ],
        "temperature": 0.5,
    }
    result = _chat(api_key, payload)
    choices = result.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"生成用户回复失败: {json.dumps(result, ensure_ascii=False)[:300]}")
    return content.strip()


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    try:
        # 步骤 1：先拿工单，拿不到会在这里抛异常，流程不会走到回复
        print("[步骤 1/2] 生成结构化工单 ...")
        ticket = create_ticket(api_key)
        print("工单:", json.dumps(ticket, ensure_ascii=False))

        # 步骤 2：工单在手，才生成用户回复
        print("[步骤 2/2] 生成用户回复 ...")
        reply = generate_reply(api_key, ticket)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print("给用户的回复:", reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
