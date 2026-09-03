#!/usr/bin/env python3
"""
weather_agent.py

一个基于智谱 GLM-5.3 模型（bigmodel.cn）的命令行天气助手，演示 Function Calling
（工具调用）的完整闭环：

    1. 把一个"查询指定城市实时天气"的函数工具描述传给模型；
    2. 模型判断需要调用工具时返回 `tool_calls`（不会真的帮你执行）；
    3. 本脚本解析 `tool_calls`，在本地执行真正的（这里是 mock 的）天气查询函数；
    4. 把函数执行结果通过 `role: "tool"` 消息回传给模型；
    5. 模型基于工具结果给出最终的自然语言回答，脚本打印这个回答。

严格使用标准库 `requests` 直接调用 `POST /paas/v4/chat/completions`，不依赖官方
`zhipuai` / `zai-sdk` SDK。

用法：
    export ZHIPUAI_API_KEY=your_api_key_here
    python weather_agent.py "北京今天天气怎么样？"
    python weather_agent.py                     # 不传参数则进入交互式输入

参考文档：智谱开放平台 bigmodel.cn，`references/chat.md`（Function Calling 一节）、
`references/models.md`（模型选型）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# 基本配置
# ---------------------------------------------------------------------------

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型选型：glm-5.3 是当前的旗舰通用对话/长程 Agent 模型，原生支持工具调用。
# 注意：glm-5.3 强制开启深度思考（thinking），无法通过 thinking.type=disabled 关闭，
# 只能用 reasoning_effort 调节思考强度（max/high/low）。见 references/models.md。
MODEL = "glm-5.3"

# API Key 从环境变量读取，绝不硬编码进代码。
# 智谱控制台申请地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

REQUEST_TIMEOUT_SECONDS = 60

# 单次“模型 -> 工具 -> 模型”闭环最多允许的往返轮数，避免模型陷入死循环连续调用工具。
MAX_TOOL_CALL_ROUNDS = 5


# ---------------------------------------------------------------------------
# 工具（函数）定义：查询指定城市的实时天气
# ---------------------------------------------------------------------------

def get_weather(city: str) -> dict[str, Any]:
    """查询指定城市的实时天气。

    真实项目里这里应该调用一个真正的天气 API（如和风天气、OpenWeatherMap 等）。
    本示例按要求返回 mock 数据，只是根据城市名做了一点点变化，方便观察效果。
    """
    mock_weather_db: dict[str, dict[str, Any]] = {
        "北京": {"temperature_c": 22, "condition": "晴", "humidity_pct": 35, "wind": "西北风 3 级"},
        "上海": {"temperature_c": 27, "condition": "多云", "humidity_pct": 58, "wind": "东南风 2 级"},
        "广州": {"temperature_c": 31, "condition": "雷阵雨", "humidity_pct": 80, "wind": "南风 2 级"},
        "深圳": {"temperature_c": 30, "condition": "多云转晴", "humidity_pct": 70, "wind": "南风 3 级"},
    }

    data = mock_weather_db.get(city)
    if data is None:
        # 没有 mock 到的城市，返回一个通用的兜底 mock 结果，而不是报错，
        # 这样模型总能拿到一个"工具结果"去组织回答。
        data = {"temperature_c": 20, "condition": "晴", "humidity_pct": 50, "wind": "微风"}

    return {
        "city": city,
        "temperature_c": data["temperature_c"],
        "condition": data["condition"],
        "humidity_pct": data["humidity_pct"],
        "wind": data["wind"],
        "source": "mock-data",  # 明确标记这是 mock 数据，避免误导
    }


# 工具的 JSON Schema 描述，随请求一起传给模型。
# `name` 需匹配 ^[a-zA-Z0-9_-]+$；`description`、`parameters` 均为必填。
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市当前的实时天气情况，包括温度、天气状况、湿度和风力信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "要查询天气的城市名称，例如：北京、上海",
                    }
                },
                "required": ["city"],
            },
        },
    }
]

# 本地"函数名 -> 可调用对象"的映射，方便按 tool_calls 里的 name 分发执行。
AVAILABLE_FUNCTIONS: dict[str, Any] = {
    "get_weather": get_weather,
}


# ---------------------------------------------------------------------------
# 调用 GLM-5.3 chat/completions 接口
# ---------------------------------------------------------------------------

def call_chat_completions(messages: list[dict[str, Any]], api_key: str) -> dict[str, Any]:
    """调用一次 /paas/v4/chat/completions（非流式），返回解析后的 JSON 响应。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",  # 目前平台只支持 "auto"，不支持强制指定某个函数
        "stream": False,
        # glm-5.3 的思考无法关闭，这里显式声明并选择中等强度，避免过度思考拖慢一次
        # 简单的工具调用问答；如需更强推理可改为 "max"。
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }

    resp = requests.post(BASE_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def build_assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    """把模型返回的 assistant 消息原样构造成可以放回 messages 历史的字典。

    需要带上 content、tool_calls，以及（若存在）reasoning_content —— 因为 glm-5.3
    强制开启思考，且工具调用场景下默认支持"交错式思考"（Interleaved Thinking），
    把 reasoning_content 一并保留有助于模型在多轮工具调用之间保持推理连贯性。
    """
    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content"),
    }
    if message.get("tool_calls"):
        assistant_message["tool_calls"] = message["tool_calls"]
    if message.get("reasoning_content") is not None:
        assistant_message["reasoning_content"] = message["reasoning_content"]
    return assistant_message


def execute_tool_call(tool_call: dict[str, Any]) -> str:
    """执行单个 tool_call，返回将写入 role="tool" 消息 content 字段的字符串。"""
    function_name = tool_call["function"]["name"]
    raw_arguments = tool_call["function"].get("arguments") or "{}"

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        return json.dumps(
            {"error": f"无法解析模型传回的参数 JSON: {exc}", "raw_arguments": raw_arguments},
            ensure_ascii=False,
        )

    func = AVAILABLE_FUNCTIONS.get(function_name)
    if func is None:
        return json.dumps({"error": f"未知的工具函数: {function_name}"}, ensure_ascii=False)

    # 简单的参数校验：调用前确认必填字段存在，不要盲目信任模型输出。
    if function_name == "get_weather" and "city" not in arguments:
        return json.dumps({"error": "缺少必填参数 city"}, ensure_ascii=False)

    try:
        result = func(**arguments)
    except TypeError as exc:
        return json.dumps({"error": f"调用 {function_name} 参数不匹配: {exc}"}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 主流程：模型 <-> 工具 的多轮闭环
# ---------------------------------------------------------------------------

def run_agent(user_query: str, api_key: str) -> str:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "你是一个乐于助人的天气助手。当用户询问某个城市的天气时，"
            "必须调用 get_weather 工具获取真实数据，不要凭空编造天气信息；"
            "拿到工具结果后，用简洁自然的中文向用户总结天气情况。",
        },
        {"role": "user", "content": user_query},
    ]

    for round_index in range(1, MAX_TOOL_CALL_ROUNDS + 1):
        response = call_chat_completions(messages, api_key)

        choice = response["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")

        # 判断是否命中函数调用：优先看 finish_reason / tool_calls 是否非空，
        # 而不是 content 是否为空（命中 tool_calls 时 content 常为 null）。
        tool_calls = message.get("tool_calls")
        if finish_reason != "tool_calls" or not tool_calls:
            # 模型已经给出最终自然语言回答，结束循环。
            return message.get("content") or ""

        print(
            f"[round {round_index}] 模型请求调用 {len(tool_calls)} 个工具: "
            f"{[tc['function']['name'] for tc in tool_calls]}",
            file=sys.stderr,
        )

        # 把 assistant 消息（含 tool_calls）原样加回历史，顺序必须紧跟在
        # 对应的 user/tool 消息之后，再接对应的 tool 消息。
        messages.append(build_assistant_message(message))

        # 一次响应可能包含多个并行的 tool_calls，需要逐个执行并各自追加一条
        # role="tool" 消息，tool_call_id 必须对应 tool_calls[].id。
        for tool_call in tool_calls:
            if tool_call.get("type") != "function":
                # 本示例只注册了 function 类型工具，其他类型（如 mcp）跳过处理。
                continue
            tool_result_content = execute_tool_call(tool_call)
            print(
                f"[round {round_index}] {tool_call['function']['name']}"
                f"({tool_call['function'].get('arguments')}) -> {tool_result_content}",
                file=sys.stderr,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result_content,
                }
            )

        # 继续下一轮循环，把工具结果传回模型，看模型是否已经可以给出最终回答，
        # 或者还需要再调用一次工具。

    raise RuntimeError(
        f"超过最大工具调用轮数（{MAX_TOOL_CALL_ROUNDS}），可能是模型陷入了重复调用工具的循环。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="基于智谱 GLM-5.3（bigmodel.cn）的命令行天气助手，演示 Function Calling。"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="要问模型的问题，例如：'北京今天天气怎么样？'。不传则进入交互式输入。",
    )
    args = parser.parse_args()

    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        print(
            f"错误：未找到环境变量 {API_KEY_ENV_VAR}。\n"
            f"请先执行：export {API_KEY_ENV_VAR}=your_api_key_here\n"
            "（API Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys）",
            file=sys.stderr,
        )
        sys.exit(1)

    user_query = args.query
    if not user_query:
        try:
            user_query = input("请输入你的问题（例如：北京今天天气怎么样？）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    if not user_query:
        print("错误：问题不能为空。", file=sys.stderr)
        sys.exit(1)

    try:
        final_answer = run_agent(user_query, api_key)
    except requests.exceptions.HTTPError as exc:
        # 打印响应体便于排查（如参数非法、模型不存在等错误信息通常在 body 里）。
        body = exc.response.text if exc.response is not None else ""
        print(f"HTTP 请求失败: {exc}\n响应内容: {body}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"网络请求异常: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n=== 最终回答 ===")
    print(final_answer)


if __name__ == "__main__":
    main()
