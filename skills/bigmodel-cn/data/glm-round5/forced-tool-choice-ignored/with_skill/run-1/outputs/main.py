"""客服工单处理：先把用户消息落成结构化工单，再基于工单生成用户回复。

业务硬性约束（顺序不可颠倒）：
  1. 必须先产出结构化工单 {"category": ..., "summary": ...}，工单是后续流程的输入；
  2. 只有拿到合法工单后才允许生成给用户的回复；拿不到工单就明确报错退出，
     绝不"只回一句安慰话"当作处理完成。

为什么不用 tools + tool_choice 强制模型调用"建单"函数：
  智谱平台的 tool_choice 仅支持字符串 "auto"（官方文档与实测一致）。传 OpenAI 风格的
  {"type":"function","function":{"name":"create_ticket"}} 不会报错，但会被静默当成
  auto 处理，模型完全可能跳过工具调用——"必须建单"这一硬性要求就失守了。
  同理 response_format 也不支持 json_schema（会被静默忽略）。
  因此这里不依赖模型"自觉"，而是由代码无条件先执行建单请求：
  response_format={"type":"json_object"} + system prompt 写明字段结构 +
  客户端 json.loads 解析与字段校验 + 失败重试兜底，全部通过后才进入回复环节。

用法：
  export ZHIPUAI_API_KEY=你的Key
  python3 main.py
"""

import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
REQUEST_TIMEOUT = 60  # 单次 HTTP 请求超时（秒）
TICKET_MAX_ATTEMPTS = 3  # 工单抽取失败重试次数上限（JSON 非法 / 字段缺失 / 请求异常）

USER_MESSAGE = "我上周买的耳机坏了，想退货"

TICKET_SYSTEM_PROMPT = (
    "你是电商客服的工单录入助手。你的唯一任务：把用户消息整理成一张结构化工单，"
    "以 JSON 对象返回，除这个 JSON 外不要输出任何解释、客套或多余文字。"
    'JSON 格式固定为：{"category": "<工单分类>", "summary": "<一句话问题摘要>"}。\n'
    "category 必须且只能从以下分类中选一个："
    "售后退换货、产品质量、物流配送、账号与支付、其他。\n"
    "summary 不超过 40 字，概括用户的核心问题与诉求。"
)

REPLY_SYSTEM_PROMPT = (
    "你是电商售后客服。回复要求：礼貌、简洁、可执行；先共情用户，"
    "再基于工单内容给出明确的下一步处理安排（如退货流程、需要准备的材料），"
    "不要向用户展示工单 JSON 或内部流程细节。"
)


class TicketError(RuntimeError):
    """结构化工单产出失败。工单是后续流程的输入，属硬性依赖，不可降级。"""


def get_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API。"
            "请先执行：export ZHIPUAI_API_KEY=你的Key"
        )
    return key


def chat(api_key: str, messages: list, json_mode: bool = False, max_tokens: int = 1024) -> str:
    """调用对话补全接口，返回模型输出的文本内容。异常一律向上抛。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        # glm-5.3 在标准端点强制开启思考且无法关闭（传 disabled 会报 1210），
        # 建单/回评均为轻量任务，用最低档降低时延。
        "reasoning_effort": "low",
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        # 尽量带出平台业务错误信息（格式为 {"error":{"code":...,"message":...}}）
        try:
            err = resp.json().get("error", {})
            detail = f"{err.get('code')}: {err.get('message')}" if err else resp.text[:200]
        except ValueError:
            detail = resp.text[:200]
        raise RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {detail}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"API 响应中没有 choices: {json.dumps(data, ensure_ascii=False)[:200]}")
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason not in ("stop", None):
        raise RuntimeError(f"模型输出异常结束（finish_reason={finish_reason}），内容不可信")
    content = (choice.get("message") or {}).get("content")
    if not content or not content.strip():
        raise RuntimeError("模型返回了空内容")
    return content.strip()


def extract_json_object(text: str) -> dict:
    """从模型输出解析 JSON 对象。json_object 模式下模型仍可能夹带围栏或解释文字，做兜底提取。"""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"无法从模型输出中解析出 JSON: {text[:200]}")
        obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError(f"模型输出的 JSON 不是对象: {text[:200]}")
    return obj


def validate_ticket(obj: dict) -> dict:
    """校验工单字段：必须是 {"category": 非空, "summary": 非空}，返回清洗后的工单。"""
    ticket = {}
    for field in ("category", "summary"):
        value = obj.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"工单缺少有效字段: {field}（原始输出: {obj}）")
        ticket[field] = value.strip()
    return ticket


def create_ticket(api_key: str, user_message: str) -> dict:
    """第一步（硬性前置）：把用户消息抽取成结构化工单。

    失败重试 TICKET_MAX_ATTEMPTS 次；仍失败则抛 TicketError，
    调用方绝不能在拿不到工单的情况下继续生成用户回复。
    """
    messages = [
        {"role": "system", "content": TICKET_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    last_error = None
    for attempt in range(1, TICKET_MAX_ATTEMPTS + 1):
        try:
            content = chat(api_key, messages, json_mode=True, max_tokens=1024)
            return validate_ticket(extract_json_object(content))
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            print(
                f"[建单] 第 {attempt}/{TICKET_MAX_ATTEMPTS} 次尝试失败: {exc}",
                file=sys.stderr,
            )
    raise TicketError(
        f"连续 {TICKET_MAX_ATTEMPTS} 次未能产出合法结构化工单，"
        f"无法进入回复环节（工单是后续流程的输入，属硬性依赖）。最后错误: {last_error}"
    )


def compose_reply(api_key: str, user_message: str, ticket: dict) -> str:
    """第二步（仅在工单就绪后调用）：把工单作为上下文，生成给用户的回复。"""
    messages = [
        {"role": "system", "content": REPLY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户消息：{user_message}\n\n"
                f"系统已生成结构化工单（作为你回复的依据）："
                f"{json.dumps(ticket, ensure_ascii=False)}\n\n"
                "请基于这张工单回复用户。"
            ),
        },
    ]
    return chat(api_key, messages, json_mode=False, max_tokens=2048)


def main() -> int:
    try:
        api_key = get_api_key()
    except RuntimeError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    # ---- 第一步：建单（硬性前置，失败即终止）----
    try:
        ticket = create_ticket(api_key, USER_MESSAGE)
    except TicketError as exc:
        print(f"[错误] 工单生成失败，未向用户发送任何回复。原因: {exc}", file=sys.stderr)
        return 1

    print("=" * 48)
    print("结构化工单（后续流程输入）:")
    print(json.dumps(ticket, ensure_ascii=False, indent=2))
    print("=" * 48)

    # ---- 第二步：基于工单生成回复（工单已就绪）----
    try:
        reply = compose_reply(api_key, USER_MESSAGE, ticket)
    except (requests.RequestException, RuntimeError) as exc:
        # 工单已产出并交付，仅回复环节失败，单独报错
        print(f"[错误] 工单已生成，但用户回复生成失败: {exc}", file=sys.stderr)
        return 1

    print("\n客服回复:")
    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
