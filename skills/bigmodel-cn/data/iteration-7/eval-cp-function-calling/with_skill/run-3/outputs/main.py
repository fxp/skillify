#!/usr/bin/env python3
"""GLM Coding Plan + requests 直连 HTTP 的 Function Calling 最小闭环示例。

流程：
  1. 定义本地工具 get_current_time(timezone)
  2. 把工具描述通过 `tools` 传给 glm-5.3，问“现在东京几点了？”
  3. 模型返回 tool_calls -> 本地执行函数 -> 以 role="tool" 消息回传
  4. 再次请求模型，打印最终自然语言回答

运行：
  export GLM_KEY="你的 GLM Coding Plan API Key"
  python3 main.py
"""

import json
import os
import sys
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

# ---------------------------------------------------------------------------
# 1. 配置
# ---------------------------------------------------------------------------
# 注意：Coding Plan 的 Key 只能打 /api/coding/paas/v4，
# 打标准端点 /api/paas/v4 会报 429 + 1113“余额不足”（不是要充值，是端点用错）。
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "glm-5.3"  # Coding Plan 可用：glm-5.3 / glm-5.3-flash

API_KEY = os.environ.get("GLM_KEY")
if not API_KEY:
    sys.exit("请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# 2. 本地工具实现
# ---------------------------------------------------------------------------
def get_current_time(timezone: str) -> dict:
    """返回指定 IANA 时区（如 Asia/Tokyo）的当前时间，纯本地实现。"""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return {"error": f"未知时区: {timezone}，请使用 IANA 时区名，如 Asia/Tokyo"}
    now = datetime.now(dt_timezone.utc).astimezone(tz)
    return {
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
    }


# 函数名 -> 可调用对象的注册表，方便按模型给的 name 分发
TOOL_REGISTRY = {"get_current_time": get_current_time}

# 传给模型的工具描述（JSON Schema）。name/description/parameters 均必填。
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
                        "description": "IANA 时区名，例如 Asia/Tokyo、Asia/Shanghai、America/New_York",
                    }
                },
                "required": ["timezone"],
            },
        },
    }
]


# ---------------------------------------------------------------------------
# 3. 调用模型
# ---------------------------------------------------------------------------
def chat(messages: list) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",  # 智谱目前只支持 "auto"
        "stream": False,
    }
    resp = requests.post(CHAT_URL, headers=HEADERS, json=payload, timeout=120)
    if resp.status_code != 200:
        # 常见：429 + {"error":{"code":"1113",...}} 说明 Key 与端点/模型不匹配
        sys.exit(f"请求失败 HTTP {resp.status_code}: {resp.text}")
    return resp.json()["choices"][0]["message"]


def run_tool_call(tool_call: dict) -> dict:
    """执行一条 tool_call，返回要回传给模型的 tool 消息。"""
    fn = tool_call["function"]
    name = fn["name"]
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except json.JSONDecodeError as e:
        result = {"error": f"参数不是合法 JSON: {e}"}
    else:
        func = TOOL_REGISTRY.get(name)
        result = func(**args) if func else {"error": f"未知函数: {name}"}
    print(f"[tool] {name}({json.dumps(args, ensure_ascii=False)}) -> {json.dumps(result, ensure_ascii=False)}")
    return {
        "role": "tool",
        "tool_call_id": tool_call["id"],  # 必须指回对应的 tool_calls[].id
        "content": json.dumps(result, ensure_ascii=False),
    }


def main() -> None:
    messages = [{"role": "user", "content": "现在东京几点了？"}]

    # 一般一次 tool call 就够；用循环兼容模型连续调用多次工具的情况
    for _ in range(5):
        message = chat(messages)
        # 把 assistant 消息原样（含 tool_calls / reasoning_content）追加进历史。
        # Coding 端点默认开启 Preserved Thinking，reasoning_content 要原样带回。
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            print("\n最终回答：", message.get("content"))
            return

        for tc in tool_calls:
            if tc.get("type") == "function":
                messages.append(run_tool_call(tc))

    sys.exit("工具调用轮数超过上限，未得到最终回答")


if __name__ == "__main__":
    main()
