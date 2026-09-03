#!/usr/bin/env python3
"""GLM Coding Plan 函数调用（Function Calling）最小示例。

流程：用户提问 -> glm-5.3 发起 tool call -> 本地执行 get_current_time -> 以 role:"tool"
消息回传 -> 打印模型最终回答。

运行前：export GLM_KEY="你的 GLM Coding Plan API Key"，然后 python3 main.py
依赖：pip install requests   （时区用标准库 zoneinfo，Python >= 3.9）
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

# Coding Plan 专用端点：比标准 API 多一级 /coding，套餐 Key 打标准端点会报 1113
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"
MAX_TOOL_ROUNDS = 5  # 防止模型反复调用工具导致死循环


# ---------------------------------------------------------------------------
# 1. 本地工具函数
# ---------------------------------------------------------------------------
def get_current_time(timezone: str) -> dict:
    """返回指定 IANA 时区（如 Asia/Tokyo）的当前时间。"""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return {"error": f"未知时区: {timezone}，请使用 IANA 时区名，如 Asia/Tokyo"}
    now = datetime.now(tz)
    return {
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
    }


# 名称 -> 可调用对象，便于按模型返回的 function.name 分发
LOCAL_TOOLS = {"get_current_time": get_current_time}

# 提供给模型的工具定义（OpenAI 风格；description / parameters 均必填）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前日期和时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名称，例如 Asia/Tokyo、Asia/Shanghai、America/New_York",
                    }
                },
                "required": ["timezone"],
            },
        },
    }
]


# ---------------------------------------------------------------------------
# 2. HTTP 调用
# ---------------------------------------------------------------------------
def chat(messages: list, api_key: str) -> dict:
    """调用一次 chat/completions，返回 choices[0].message。"""
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",  # 智谱目前只支持 "auto"
        },
        timeout=120,
    )
    if resp.status_code != 200:
        body = resp.text
        if '"1113"' in body:
            print(
                "错误 1113（余额不足）：套餐 Key 请确认 Base URL 是 "
                "…/api/coding/paas/v4，且模型为 glm-5.3 / glm-5.3-flash；"
                "不是让你去充值。",
                file=sys.stderr,
            )
        print(f"HTTP {resp.status_code}: {body}", file=sys.stderr)
        resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]


# ---------------------------------------------------------------------------
# 3. 工具调用循环
# ---------------------------------------------------------------------------
def run_tool_calls(tool_calls: list) -> list:
    """执行模型请求的每个函数，返回对应的 role:"tool" 消息列表。"""
    tool_messages = []
    for tc in tool_calls:
        if tc.get("type") != "function":
            continue
        name = tc["function"]["name"]
        raw_args = tc["function"].get("arguments") or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {}
            result = {"error": f"参数不是合法 JSON: {raw_args}"}
        else:
            func = LOCAL_TOOLS.get(name)
            if func is None:
                result = {"error": f"未知函数: {name}"}
            else:
                try:
                    result = func(**args)
                except TypeError as e:
                    result = {"error": f"参数错误: {e}"}
        print(f"[tool] {name}({json.dumps(args, ensure_ascii=False)}) -> "
              f"{json.dumps(result, ensure_ascii=False)}")
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],  # 必须指回 assistant.tool_calls[].id
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    return tool_messages


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）")

    question = "现在东京几点了？"
    print(f"[user] {question}")
    messages = [{"role": "user", "content": question}]

    for _ in range(MAX_TOOL_ROUNDS):
        message = chat(messages, api_key)

        # 把 assistant 消息原样（含 tool_calls、reasoning_content）加回历史。
        # Coding 端点默认开启 Preserved Thinking，reasoning_content 需完整回传。
        history_msg = {"role": "assistant", "content": message.get("content")}
        if message.get("reasoning_content"):
            history_msg["reasoning_content"] = message["reasoning_content"]
        if message.get("tool_calls"):
            history_msg["tool_calls"] = message["tool_calls"]
        messages.append(history_msg)

        # 判断是否函数调用：看 tool_calls 是否非空，而不是 content 是否为空
        if not message.get("tool_calls"):
            print(f"[assistant] {message.get('content')}")
            return

        messages.extend(run_tool_calls(message["tool_calls"]))

    sys.exit(f"超过 {MAX_TOOL_ROUNDS} 轮工具调用仍未得到最终回答，已中止")


if __name__ == "__main__":
    main()
