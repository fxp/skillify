#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan(个人版 Medium 套餐)Anthropic 协议入口最小示例。

- 入口:https://ark.cn-beijing.volces.com/api/plan(Anthropic 兼容层,Messages 端点为 /v1/messages)
- 模型:doubao-seed-2.0-lite(套餐文本生成"标准"档,抵扣系数低;成本敏感场景必须由它服务)
- 核对:同时打印"我请求的模型"与"服务端实际返回的模型"(响应体 model 字段),
  二者不一致时显式报警并以非零退出码结束。
- 依赖:仅 requests;API Key 从环境变量 ARK_AGENT_PLAN_API_KEY 读取。
"""

import os
import sys

import requests

# Agent Plan 的 Anthropic 协议入口(注意不是 OpenAI 兼容的 /api/plan/v3)
ANTHROPIC_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_URL = ANTHROPIC_BASE_URL.rstrip("/") + "/v1/messages"

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

# 成本护栏:只允许这个模型服务,被路由到其他模型(抵扣系数差数倍)即报警
REQUESTED_MODEL = "doubao-seed-2.0-lite"


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"[错误] 未设置环境变量 {API_KEY_ENV},请先执行:export {API_KEY_ENV}=<你的Agent Plan API Key>")
        return 2

    headers = {
        # Anthropic 协议标准鉴权头
        "x-api-key": api_key,
        # 方舟兼容层同时接受 Claude Code 风格的 Bearer 头,一并带上以兼容两种接入方式
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": 128,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Python"},
        ],
    }

    print(f"请求端点        : {MESSAGES_URL}")
    print(f"我请求的模型    : {REQUESTED_MODEL}")
    print("-" * 60)

    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"[错误] 网络请求失败: {exc}")
        return 2

    if resp.status_code != 200:
        print(f"[错误] HTTP {resp.status_code}: {resp.text[:2000]}")
        return 2

    try:
        data = resp.json()
    except ValueError:
        print(f"[错误] 响应不是合法 JSON: {resp.text[:2000]}")
        return 2

    # Anthropic Messages 响应的 model 字段 = 实际服务模型的回显
    served_model = data.get("model") or ""
    answer = "".join(
        block.get("text", "") for block in data.get("content", []) if isinstance(block, dict)
    )
    usage = data.get("usage") or {}

    print(f"模型回答        : {answer.strip()}")
    print(f"token 用量      : 输入 {usage.get('input_tokens', '?')} / 输出 {usage.get('output_tokens', '?')}")
    print("-" * 60)
    print(f"我请求的模型    : {REQUESTED_MODEL}")
    print(f"服务端返回的模型: {served_model or '(响应中无 model 字段)'}")

    if served_model != REQUESTED_MODEL:
        print(
            f"\n[报警] 模型不一致!请求的是 {REQUESTED_MODEL},实际服务的是 "
            f"{served_model or '(未知)'}。\n"
            "        两者抵扣系数可能相差数倍,继续调用会产生意外费用;请停止使用并核查\n"
            "        套餐配置/模型路由(若回显为同名模型带日期后缀的版本快照,也请先人工确认再放行)。"
        )
        return 1

    print("\n[核对通过] 请求模型与服务端实际服务模型一致,均为 doubao-seed-2.0-lite。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
