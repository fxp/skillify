#!/usr/bin/env python3
"""
GLM Coding Plan + requests 的 Function Calling 最小示例。

流程:
  1. 带 tools 定义向 glm-5.3 提问「现在东京几点了?」
  2. 模型返回 tool_calls -> 本地执行 get_current_time(timezone)
  3. 以 role=tool 消息把结果回传给模型
  4. 打印模型的最终回答

运行:
  export GLM_KEY=你的key
  python3 main.py
"""

import json
import os
import sys
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

# GLM Coding Plan 专用 endpoint; 如需改用普通开放平台 endpoint,
# 设置 GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4 即可
BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
CHAT_URL = f"{BASE_URL.rstrip('/')}/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


# ---------------------------------------------------------------------------
# 1. 本地工具函数
# ---------------------------------------------------------------------------
def get_current_time(timezone: str = "UTC") -> dict:
    """返回指定 IANA 时区(如 Asia/Tokyo)的当前时间。"""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return {"error": f"unknown timezone: {timezone}"}
    now = datetime.now(tz)
    return {
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
    }


# 工具名 -> 本地实现 的映射
TOOL_REGISTRY = {
    "get_current_time": get_current_time,
}

# 发给模型的工具描述(OpenAI 兼容格式)
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
                        "description": "IANA 时区名称,例如 Asia/Tokyo、Asia/Shanghai、America/New_York",
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
    """调用 chat/completions,返回 choices[0].message。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
    }
    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")
    return data["choices"][0]["message"]


def execute_tool_call(tool_call: dict) -> str:
    """执行单个 tool call,返回 JSON 字符串作为 tool 消息内容。"""
    fn = tool_call["function"]
    name = fn["name"]
    raw_args = fn.get("arguments") or "{}"
    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

    impl = TOOL_REGISTRY.get(name)
    if impl is None:
        result = {"error": f"unknown tool: {name}"}
    else:
        try:
            result = impl(**args)
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}

    print(f"[tool] {name}({json.dumps(args, ensure_ascii=False)}) -> {json.dumps(result, ensure_ascii=False)}")
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 3. 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误: 请先设置环境变量 GLM_KEY", file=sys.stderr)
        return 1

    question = "现在东京几点了?"
    messages = [
        {"role": "system", "content": "你是一个乐于助人的助手。需要查询时间时请调用工具,不要自行猜测。"},
        {"role": "user", "content": question},
    ]
    print(f"[user] {question}")

    # 允许模型多轮调用工具,直到给出最终回答
    for _ in range(5):
        message = chat(messages, api_key)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            print(f"\n[assistant] {message.get('content', '').strip()}")
            return 0

        # 把模型的 assistant 消息(含 tool_calls)原样加入历史
        assistant_msg = {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        # 逐个执行工具并回传结果
        for tc in tool_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": execute_tool_call(tc),
                }
            )

    print("错误: 工具调用轮数过多,未得到最终回答", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
