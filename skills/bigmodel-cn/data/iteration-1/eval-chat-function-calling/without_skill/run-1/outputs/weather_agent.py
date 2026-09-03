#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_agent.py

一个基于智谱 GLM-5.3（bigmodel.cn）的命令行助手示例，演示如何通过
标准库 `requests` 直接调用 bigmodel.cn 的 Chat Completions HTTP 接口，
实现工具调用（function calling）。

流程：
1. 定义一个"查询指定城市实时天气"的工具（函数）描述，随对话一起发给模型。
2. 模型认为需要调用工具时，会在响应中返回 `tool_calls`（不直接给出最终答案）。
3. 脚本本地执行对应的 Python 函数（这里返回 mock 数据，不访问真实天气 API），
   并把函数的返回结果以 role="tool" 的消息追加回对话历史。
4. 把包含工具结果的完整对话历史再次发给模型，模型基于工具结果生成
   最终的自然语言回答并打印出来。

使用方法：
    export BIGMODEL_API_KEY="你的真实 API Key"   # 未设置时使用占位符，无法真实调用
    python weather_agent.py "北京今天天气怎么样？"

注意：
- 本脚本不使用智谱官方 SDK（zhipuai），只用 `requests` 直接调用 HTTP 接口。
- API Key 从环境变量 BIGMODEL_API_KEY 读取，避免把密钥硬编码在代码里。
- 天气查询函数 `get_current_weather` 返回的是 mock（模拟）数据，
  没有真实联网查询天气，仅用于演示 function calling 的完整闭环。
"""

import json
import os
import sys
import uuid
import random
from typing import Any, Dict, List, Optional

import requests

# --------------------------------------------------------------------------
# 基本配置
# --------------------------------------------------------------------------

# 智谱开放平台（bigmodel.cn）的 Chat Completions 接口地址。
# 该接口与 OpenAI 的 Chat Completions 协议基本兼容，支持 tools / tool_calls。
BIGMODEL_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 使用的模型名称，按任务要求写死为 glm-5.3（如后续该型号名称有变化，按官方文档调整即可）。
MODEL_NAME = "glm-5.3"

# API Key 从环境变量读取；未设置时使用占位符，脚本仍可运行到"组装请求"这一步，
# 但真正发起 HTTP 请求会因为鉴权失败而报错（因为我们没有真实的 Key）。
API_KEY = os.environ.get("BIGMODEL_API_KEY", "YOUR_BIGMODEL_API_KEY_PLACEHOLDER")

REQUEST_TIMEOUT_SECONDS = 60
MAX_TOOL_CALL_ROUNDS = 5  # 防止模型陷入死循环反复调用工具，设置一个安全上限


# --------------------------------------------------------------------------
# 工具（函数）定义与实现
# --------------------------------------------------------------------------

def get_current_weather(city: str, unit: str = "celsius") -> Dict[str, Any]:
    """
    查询指定城市的实时天气。

    这里没有接入真实的天气服务，而是返回一份结构固定、内容随机的 mock 数据，
    用来演示"模型决定调用工具 -> 脚本本地执行 -> 结果回传给模型"的完整链路。

    Args:
        city: 城市名称，例如 "北京"、"上海"、"San Francisco"。
        unit: 温度单位，"celsius"（摄氏度）或 "fahrenheit"（华氏度），默认摄氏度。

    Returns:
        一个字典，包含城市、温度、天气状况、湿度、风速等字段。
    """
    conditions = ["晴", "多云", "阴", "小雨", "雷阵雨", "大风"]

    if unit == "fahrenheit":
        temperature = random.randint(50, 95)
    else:
        unit = "celsius"
        temperature = random.randint(10, 35)

    mock_result = {
        "city": city,
        "temperature": temperature,
        "unit": unit,
        "condition": random.choice(conditions),
        "humidity_percent": random.randint(30, 90),
        "wind_speed_kmh": round(random.uniform(0, 40), 1),
        "note": "这是 mock 数据，仅用于演示 function calling，非真实天气。",
    }
    return mock_result


# 提供给模型的工具（函数）JSON Schema 描述。
# 结构遵循 OpenAI / 智谱兼容的 "tools" 格式：
# {"type": "function", "function": {"name", "description", "parameters": <JSON Schema>}}
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "查询指定城市当前的实时天气情况，包括温度、天气状况、湿度和风速。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "要查询天气的城市名称，例如：北京、上海、San Francisco。",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "返回的温度单位，默认为 celsius（摄氏度）。",
                    },
                },
                "required": ["city"],
            },
        },
    }
]

# 函数名 -> 本地可调用实现的映射表，方便根据模型返回的 tool_call.function.name 分发执行。
AVAILABLE_FUNCTIONS = {
    "get_current_weather": get_current_weather,
}


# --------------------------------------------------------------------------
# 与 bigmodel.cn 的 HTTP 交互
# --------------------------------------------------------------------------

def call_bigmodel_chat_completions(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    直接用 requests 调用 bigmodel.cn 的 Chat Completions HTTP 接口。

    Args:
        messages: 对话消息列表（OpenAI 风格的 messages 数组）。
        tools: 工具（函数）描述列表；不需要工具调用时可传 None。

    Returns:
        接口返回的 JSON（已反序列化为 dict）。

    Raises:
        requests.HTTPError: 当 HTTP 状态码非 2xx 时抛出。
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
    }
    if tools:
        payload["tools"] = tools
        # "auto" 表示由模型自行判断是否需要调用工具（也可以强制指定某个工具）。
        payload["tool_choice"] = "auto"

    response = requests.post(
        BIGMODEL_API_URL,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


# --------------------------------------------------------------------------
# 工具调用循环（core agent loop）
# --------------------------------------------------------------------------

def run_agent(user_question: str) -> str:
    """
    执行一次完整的"用户提问 -> 模型决策 -> （可能）本地执行工具 -> 模型给出最终答案"流程。

    Args:
        user_question: 用户在命令行输入的问题。

    Returns:
        模型综合工具结果后给出的最终自然语言回答。
    """
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是一个可以调用工具的天气助手。当用户询问某个城市的实时天气时，"
                "必须调用 get_current_weather 工具获取数据，再基于工具返回的结果，"
                "用简洁自然的中文回答用户。不要在没有调用工具的情况下凭空编造天气数据。"
            ),
        },
        {"role": "user", "content": user_question},
    ]

    for round_index in range(MAX_TOOL_CALL_ROUNDS):
        response_json = call_bigmodel_chat_completions(messages, tools=TOOLS_SCHEMA)

        choice = response_json["choices"][0]
        finish_reason = choice.get("finish_reason")
        assistant_message = choice["message"]

        # 把模型这一轮的回复（可能包含 tool_calls，也可能是最终答案）加入历史，
        # 保持对话上下文完整，供下一轮请求使用。
        messages.append(assistant_message)

        tool_calls = assistant_message.get("tool_calls")

        if finish_reason == "tool_calls" and tool_calls:
            # 模型决定调用一个或多个工具：逐个在本地执行，并把结果回传。
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                raw_arguments = tool_call["function"].get("arguments") or "{}"

                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}

                print(
                    f"[调试] 模型请求调用工具: {function_name}，参数: {arguments}",
                    file=sys.stderr,
                )

                function_to_call = AVAILABLE_FUNCTIONS.get(function_name)
                if function_to_call is None:
                    function_result: Dict[str, Any] = {
                        "error": f"未知工具: {function_name}"
                    }
                else:
                    function_result = function_to_call(**arguments)

                # 工具调用结果需以 role="tool" 的消息形式回传，
                # 且必须携带对应的 tool_call_id，模型才能对上号。
                tool_call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(function_result, ensure_ascii=False),
                    }
                )

            # 带着工具结果继续下一轮请求，让模型生成最终回答（或再次调用工具）。
            continue

        # finish_reason 不是 tool_calls，说明模型已经给出最终答案。
        final_answer = assistant_message.get("content") or ""
        return final_answer

    return "（已达到最大工具调用轮数，未能获得最终答案。）"


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) > 1:
        user_question = " ".join(sys.argv[1:])
    else:
        user_question = "请问北京现在的天气怎么样？"

    if API_KEY == "YOUR_BIGMODEL_API_KEY_PLACEHOLDER":
        print(
            "[警告] 未检测到环境变量 BIGMODEL_API_KEY，当前使用占位符 Key，"
            "真实请求会因鉴权失败而报错。请先执行:\n"
            '    export BIGMODEL_API_KEY="你的真实 API Key"\n',
            file=sys.stderr,
        )

    print(f"用户提问: {user_question}\n")

    try:
        final_answer = run_agent(user_question)
    except requests.HTTPError as exc:
        print(f"调用 bigmodel.cn 接口失败: {exc}", file=sys.stderr)
        if exc.response is not None:
            print(f"响应内容: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"网络请求异常: {exc}", file=sys.stderr)
        sys.exit(1)

    print("模型最终回答:")
    print(final_answer)


if __name__ == "__main__":
    main()
