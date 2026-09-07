#!/usr/bin/env python3
"""通过火山方舟 Agent Plan 的 Anthropic 协议入口发送一次对话请求。

- 入口:Agent Plan 专属 Anthropic 协议 Base URL
  https://ark.cn-beijing.volces.com/api/plan + /v1/messages
- 模型:doubao-seed-2.0-lite(成本敏感场景,必须确保服务端实际使用该模型)
- 校验:对比「我请求的模型」与「响应体 model 字段(服务端实际回给我的模型)」,
  不一致或缺失时明确报警并以非零退出码结束。

用法:
    export ARK_AGENT_PLAN_API_KEY=<你的 Agent Plan API Key>
    python3 main.py

退出码:
    0  请求成功且模型一致
    1  请求本身失败(缺 Key / 网络错误 / HTTP 非 200 / 响应非法)
    2  请求成功但模型不一致(或响应缺少 model 字段,无法核对)
"""

import os
import sys

import requests

# Agent Plan 个人版专属的 Anthropic 协议 Base URL(官方文档:其他 Base URL 无法在 Agent Plan 中使用)
ANTHROPIC_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_ENDPOINT = ANTHROPIC_BASE_URL.rstrip("/") + "/v1/messages"

# 本场景必须锁定的模型:套餐内各模型抵扣系数差数倍,不可被替换
REQUESTED_MODEL = "doubao-seed-2.0-lite"

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
REQUEST_TIMEOUT_SECONDS = 60
MAX_TOKENS = 256
USER_QUESTION = "用一句话介绍 Python"


def fail(message: str) -> int:
    print(f"[错误] {message}", file=sys.stderr)
    return 1


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        return fail(f"未配置 API Key,请先执行:export {API_KEY_ENV}=<你的 Agent Plan API Key>")

    headers = {
        "Content-Type": "application/json",
        # Agent Plan 文档以 ANTHROPIC_AUTH_TOKEN 方式鉴权(即 Bearer Token);
        # 同时携带 x-api-key,兼容 Anthropic 协议原生的两种鉴权写法。
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": USER_QUESTION}],
    }

    print(f"请求端点: {MESSAGES_ENDPOINT}")
    print(f"我请求的模型: {REQUESTED_MODEL}")
    print("-" * 60)

    try:
        response = requests.post(
            MESSAGES_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return fail(f"请求失败: {exc}")

    if response.status_code != 200:
        return fail(f"HTTP {response.status_code},响应内容: {response.text[:2000]}")

    try:
        data = response.json()
    except ValueError:
        return fail(f"响应不是合法 JSON: {response.text[:2000]}")

    # 提取回复文本(Anthropic Messages 格式:content 为块数组)
    answer = "\n".join(
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    print(f"模型回复: {answer}")

    usage = data.get("usage") or {}
    print(f"token 用量: input={usage.get('input_tokens')} output={usage.get('output_tokens')}")

    # ---- 模型核对:响应体 model 字段即服务端实际服务的模型 ----
    served_model = data.get("model")
    print("-" * 60)
    print(f"我请求的模型: {REQUESTED_MODEL}")
    print(f"服务端实际回给我的模型: {served_model!r}")

    if not served_model or not str(served_model).strip():
        print(
            "[警告] ⚠️  响应中缺少 model 字段,无法核对实际服务的模型!"
            " 为避免被计到高价模型,请到方舟控制台的用量明细中人工核实。",
            file=sys.stderr,
        )
        return 2

    if str(served_model).strip() != REQUESTED_MODEL:
        print(
            f"[警告] ⚠️  模型不一致!请求的是 {REQUESTED_MODEL},"
            f"服务端实际服务的是 {served_model}。两者抵扣系数不同,继续使用将产生额外成本,请立即排查。",
            file=sys.stderr,
        )
        return 2

    print("[核对] ✅ 模型一致,确认为 doubao-seed-2.0-lite 服务。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
