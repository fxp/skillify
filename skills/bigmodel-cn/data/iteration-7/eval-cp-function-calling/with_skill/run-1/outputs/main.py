#!/usr/bin/env python3
"""
用 GLM Coding Plan（编程套餐）Key + 原生 HTTP（requests）跑通一次完整的 Function Calling 闭环：

  用户提问 -> glm-5.3 返回 tool_calls -> 本地执行 get_current_time -> 以 role="tool" 回传 -> 打印最终回答

运行：
  export GLM_KEY="你的 GLM Coding Plan API Key"
  python3 main.py

要点（来自智谱官方文档 + 实测）：
  * Coding Plan 的 Key 与标准 API Key 不通用，Base URL 必须是
    https://open.bigmodel.cn/api/coding/paas/v4 （比标准端点多一层 /coding）。
    套餐 Key 打到标准端点 .../api/paas/v4 会报 HTTP 429 + code 1113 "余额不足"，这不是要充值。
  * 套餐内可用的对话模型是 glm-5.3 / glm-5.3-flash。
  * 请求体字段与标准端点完全一致（OpenAI 风格 tools / tool_calls / role=tool）。
  * Coding 端点默认开启 Preserved Thinking：把 assistant 消息加回历史时要原样带上 reasoning_content。
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

# ---------- 配置 ----------
API_KEY = os.environ.get("GLM_KEY")
# 注意：Coding Plan 专用端点，路径里有 /coding；不要在后面再拼 /v1
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "glm-5.3"
TIMEOUT = 120  # 秒；glm-5.3 带思考，响应可能较慢
MAX_ROUNDS = 5  # 防止模型反复发起工具调用导致死循环


# ---------- 本地工具实现 ----------
def get_current_time(timezone: str) -> dict:
    """返回指定 IANA 时区（如 Asia/Tokyo）的当前时间。纯本地实现，不联网。"""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return {"error": f"未知时区: {timezone!r}，请使用 IANA 时区名，例如 Asia/Tokyo"}
    now = datetime.now(tz)
    return {
        "timezone": timezone,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
    }


# 模型可调用的工具注册表：函数名 -> Python 函数
TOOL_REGISTRY = {"get_current_time": get_current_time}

# 传给模型的工具定义（OpenAI 风格；name/description/parameters 均必填）
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


# ---------- HTTP 调用 ----------
def chat(messages: list) -> dict:
    """调用一次 chat/completions，返回 choices[0].message。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",  # 智谱目前只支持 "auto"
    }
    resp = requests.post(
        CHAT_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )

    if resp.status_code != 200:
        # 常见错误友好提示
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code = str(err.get("code", ""))
        msg = err.get("message", resp.text)
        hint = ""
        if code == "1113":
            hint = (
                "\n提示：1113 通常不是真的余额不足。请检查："
                "\n  1) GLM_KEY 是否为 GLM Coding Plan 套餐 Key（不是开放平台按量 Key）；"
                "\n  2) Base URL 是否为 https://open.bigmodel.cn/api/coding/paas/v4；"
                "\n  3) 模型是否为 glm-5.3 / glm-5.3-flash；"
                "\n  4) 套餐 5 小时 / 每周额度是否用尽。"
            )
        elif resp.status_code == 401:
            hint = "\n提示：鉴权失败，请确认 GLM_KEY 正确且未过期。"
        sys.exit(f"请求失败 HTTP {resp.status_code}，code={code}: {msg}{hint}")

    data = resp.json()
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason in ("sensitive", "network_error", "model_context_window_exceeded"):
        sys.exit(f"模型异常结束，finish_reason={finish_reason}")
    return choice["message"]


# ---------- 主流程 ----------
def main() -> None:
    if not API_KEY:
        sys.exit("未找到环境变量 GLM_KEY，请先 export GLM_KEY=<你的 GLM Coding Plan API Key>")

    question = "现在东京几点了？"
    print(f"[用户] {question}")

    messages = [
        {
            "role": "system",
            "content": "你是一个助手。涉及当前时间的问题必须调用 get_current_time 工具获取，不要自行猜测。",
        },
        {"role": "user", "content": question},
    ]

    for _ in range(MAX_ROUNDS):
        message = chat(messages)

        # 把 assistant 消息原样加回历史（含 tool_calls 与 reasoning_content），
        # Coding 端点默认开启 Preserved Thinking，reasoning_content 需完整、未修改地回传。
        assistant_msg = {"role": "assistant", "content": message.get("content")}
        if message.get("reasoning_content"):
            assistant_msg["reasoning_content"] = message["reasoning_content"]
        if message.get("tool_calls"):
            assistant_msg["tool_calls"] = message["tool_calls"]
        messages.append(assistant_msg)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # 没有工具调用 -> 这就是最终回答
            print(f"[模型] {message.get('content')}")
            return

        # 可能一次返回多个 tool_calls，逐个执行并各自回传一条 tool 消息
        for tc in tool_calls:
            if tc.get("type") != "function":
                continue
            fn_name = tc["function"]["name"]
            raw_args = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            print(f"[工具调用] {fn_name}({json.dumps(args, ensure_ascii=False)})")

            fn = TOOL_REGISTRY.get(fn_name)
            if fn is None:
                result = {"error": f"未知工具: {fn_name}"}
            else:
                try:
                    result = fn(**args)
                except TypeError as e:
                    result = {"error": f"参数错误: {e}"}
            print(f"[工具结果] {json.dumps(result, ensure_ascii=False)}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],  # 必须指回对应的 tool_calls[].id
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        # 回到循环顶部：把工具结果发回模型，拿最终回答

    sys.exit(f"超过 {MAX_ROUNDS} 轮仍未得到最终回答，已终止。")


if __name__ == "__main__":
    main()
