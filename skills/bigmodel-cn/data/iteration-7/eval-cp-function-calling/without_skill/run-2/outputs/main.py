#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱 GLM Coding Plan — 用 requests 直接调 HTTP 完成一次 function calling 闭环。

流程：
  1. 定义本地工具 get_current_time(timezone)
  2. 把工具 schema 通过 `tools` 字段发给 glm-5.3，提问「现在东京几点了？」
  3. 模型返回 tool_calls -> 脚本本地执行函数
  4. 把结果以 role=tool 的消息回传给模型
  5. 打印模型的最终回答

运行：
  export GLM_KEY=your_api_key
  python3 main.py
"""

import json
import os
import sys
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo  # Python 3.9+ 标准库

import requests

# Coding Plan 专用端点（与普通 API 的 /api/paas/v4 区分开）。
# 如需切回通用端点，可设置环境变量 GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
CHAT_URL = f"{BASE_URL.rstrip('/')}/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


# ---------------------------------------------------------------------------
# 1. 本地工具实现
# ---------------------------------------------------------------------------
def get_current_time(timezone: str = "UTC") -> str:
    """返回指定 IANA 时区的当前时间（本地计算，不依赖网络）。"""
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        return json.dumps(
            {"error": f"unknown timezone: {timezone}", "hint": "use IANA name like Asia/Tokyo"},
            ensure_ascii=False,
        )
    now = datetime.now(dt_timezone.utc).astimezone(tz)
    return json.dumps(
        {
            "timezone": timezone,
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "utc_offset": now.strftime("%z"),
            "weekday": now.strftime("%A"),
        },
        ensure_ascii=False,
    )


# 工具名 -> 本地可调用对象
TOOL_REGISTRY = {"get_current_time": get_current_time}

# 发给模型的工具 schema（OpenAI 兼容格式）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取指定时区的当前日期和时间。",
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
# 2. HTTP 调用封装
# ---------------------------------------------------------------------------
def chat(messages, api_key, tools=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        print(f"[HTTP {resp.status_code}] {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    data = resp.json()
    if "choices" not in data:
        raise RuntimeError(f"unexpected response: {json.dumps(data, ensure_ascii=False)}")
    return data["choices"][0]["message"]


def run_tool_call(tool_call):
    """执行单个 tool_call，返回可直接 append 到 messages 的 tool 消息。"""
    fn_name = tool_call["function"]["name"]
    raw_args = tool_call["function"].get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        args = {}

    fn = TOOL_REGISTRY.get(fn_name)
    if fn is None:
        result = json.dumps({"error": f"unknown tool: {fn_name}"}, ensure_ascii=False)
    else:
        result = fn(**args)

    print(f"[tool] {fn_name}({args}) -> {result}")
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": result,
    }


# ---------------------------------------------------------------------------
# 3. 主流程
# ---------------------------------------------------------------------------
def main():
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("请先设置环境变量 GLM_KEY（智谱 API Key）", file=sys.stderr)
        sys.exit(1)

    question = "现在东京几点了？"
    messages = [
        {"role": "system", "content": "你是一个乐于助人的助手。需要知道当前时间时，请调用工具而不是猜测。"},
        {"role": "user", "content": question},
    ]
    print(f"[user] {question}")

    # 允许多轮工具调用（模型可能连续调用多次工具），设置上限防止死循环
    for _ in range(5):
        msg = chat(messages, api_key, tools=TOOLS)
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            print(f"\n[assistant] {msg.get('content', '')}")
            return

        # 把模型的 assistant 消息（含 tool_calls）原样放回上下文
        assistant_msg = {
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": tool_calls,
        }
        messages.append(assistant_msg)

        # 逐个执行工具并回传结果
        for tc in tool_calls:
            messages.append(run_tool_call(tc))

    print("[warn] 超过最大工具调用轮数，退出。", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
