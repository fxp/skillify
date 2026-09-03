#!/usr/bin/env python3
"""
用 requests 直接调用智谱 GLM(OpenAI 兼容格式)完成一次 function calling:
  1. 定义本地工具 get_current_time(timezone)
  2. 让 glm-5.3 回答“现在东京几点了?”
  3. 模型发起 tool call -> 本地执行 -> 以 role=tool 消息回传 -> 打印最终回答

运行:
  export GLM_KEY="你的 API Key"
  python3 main.py
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# GLM Coding Plan 订阅使用专属的 coding 端点; 普通按量付费用户可通过
# GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4 覆盖。
BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")
CHAT_URL = f"{BASE_URL.rstrip('/')}/chat/completions"


# ---------- 1. 本地工具实现 ----------
def get_current_time(timezone: str) -> str:
    """返回指定 IANA 时区(如 Asia/Tokyo)的当前时间。"""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return json.dumps({"error": f"unknown timezone: {timezone}"}, ensure_ascii=False)
    now = datetime.now(tz)
    return json.dumps(
        {
            "timezone": timezone,
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "utc_offset": now.strftime("%z"),
            "weekday": now.strftime("%A"),
        },
        ensure_ascii=False,
    )


TOOL_IMPLS = {"get_current_time": get_current_time}

# ---------- 2. 给模型的工具描述 (OpenAI tools 格式) ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前时间。timezone 使用 IANA 时区名，例如 Asia/Tokyo、Asia/Shanghai、America/New_York。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名称，例如 Asia/Tokyo",
                    }
                },
                "required": ["timezone"],
            },
        },
    }
]


# ---------- 3. HTTP 调用 ----------
def chat(messages, api_key):
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        print(f"请求失败 HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    if "error" in data:
        print(f"API 返回错误: {data['error']}", file=sys.stderr)
        sys.exit(1)
    return data["choices"][0]["message"]


def main():
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("请先设置环境变量 GLM_KEY", file=sys.stderr)
        sys.exit(1)

    messages = [
        {"role": "system", "content": "你是一个乐于助人的助手。需要知道当前时间时必须调用 get_current_time 工具，不要自己猜测。"},
        {"role": "user", "content": "现在东京几点了？"},
    ]

    # 循环处理: 模型可能连续发起多轮工具调用，直到给出最终文本回答
    for _ in range(5):
        msg = chat(messages, api_key)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            print("\n=== 模型最终回答 ===")
            print(msg.get("content", ""))
            return

        # 把 assistant 的 tool_calls 消息原样放回上下文
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        # 逐个执行工具, 以 role=tool 消息回传
        for call in tool_calls:
            fn_name = call["function"]["name"]
            raw_args = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            print(f"[tool call] {fn_name}({args})")

            impl = TOOL_IMPLS.get(fn_name)
            result = impl(**args) if impl else json.dumps({"error": f"unknown tool {fn_name}"})
            print(f"[tool result] {result}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )

    print("超过最大工具调用轮数，未得到最终回答", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
