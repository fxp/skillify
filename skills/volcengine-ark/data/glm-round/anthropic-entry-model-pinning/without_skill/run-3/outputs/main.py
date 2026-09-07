#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火山方舟 Agent Plan（个人版 Medium 套餐）—— Anthropic 协议入口调用示例。

用途：
    通过 Agent Plan 的 Anthropic 兼容入口发送一次对话请求（问"用一句话介绍 Python"），
    并严格核对「我请求的模型」与「服务端实际服务的模型」。

为什么必须核对：
    Agent Plan 套餐内不同模型的额度抵扣系数相差可达数倍。官方文档说明响应中的
    model 字段可能带具体版本号后缀（与请求时传入的通用模型名不完全一致），且存在
    服务端回退（fallback）机制——若请求的模型名不可用，可能被悄悄路由到别的模型，
    成本会被放大。因此每次调用后必须以响应体 model 字段为准做核对。

已核实的接口事实（火山方舟官方文档及接入指南）：
    - Agent Plan 的 Anthropic 兼容 Base URL：
        https://ark.cn-beijing.volces.com/api/plan
      （注意：OpenAI 兼容入口是 /api/plan/v3，按量付费的 /api/v3/anthropic
        均不是 Agent Plan 的正确入口）
    - Messages 端点：{BASE_URL}/v1/messages
    - 认证头：x-api-key: <API Key>（Claude Code 生态亦兼容 Authorization: Bearer，
      此处两者同时携带，兼容网关两种取值方式）
    - 协议版本头：anthropic-version: 2023-06-01
    - 响应体 content 为分块数组，文本在 type == "text" 的块中；顶层 model 字段
      为服务端实际服务的模型名。

运行方式：
    export ARK_AGENT_PLAN_API_KEY=<你的 Agent Plan API Key>
    python3 main.py
"""

import os
import sys

import requests

# Agent Plan 的 Anthropic 协议兼容 Base URL（勿加 /v3，那是 OpenAI 协议路径）
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_URL = BASE_URL + "/v1/messages"

# 本脚本要求服务的模型：必须是它，不能被路由/回退到别的模型。
# Agent Plan 套餐内的通用模型名写法（不带日期快照后缀）。
REQUESTED_MODEL = "doubao-seed-2.0-lite"

# Anthropic Messages 协议要求必填 max_tokens；一句话回答 256 足够。
MAX_TOKENS = 256
TIMEOUT_SECONDS = 60


def load_api_key() -> str:
    """从环境变量 ARK_AGENT_PLAN_API_KEY 读取 API Key，缺失则直接报错退出。"""
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ARK_AGENT_PLAN_API_KEY。")
        print("请先执行：export ARK_AGENT_PLAN_API_KEY=<你的 Agent Plan API Key>")
        sys.exit(1)
    return api_key


def send_message(api_key: str) -> dict:
    """通过 Anthropic 协议入口发送一次对话请求，返回解析后的 JSON（出错则退出）。"""
    headers = {
        "Content-Type": "application/json",
        # 两种认证头同时携带：Anthropic 官方协议用 x-api-key，
        # Claude Code / 网关生态亦接受 Authorization: Bearer，值相同。
        "x-api-key": api_key,
        "Authorization": "Bearer " + api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": "用一句话介绍 Python",
            }
        ],
    }

    print("请求端点: {}".format(MESSAGES_URL))
    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload,
                             timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        print("错误：请求失败（网络或超时）：{}".format(exc))
        sys.exit(1)

    if resp.status_code != 200:
        # 常见错误：401/403 = Key 无效；404 = 入口路径或模型名不对；
        # 429 = 套餐额度不足或限流。打印响应体便于排查。
        print("错误：HTTP {}".format(resp.status_code))
        print("响应体：{}".format(resp.text[:2000]))
        sys.exit(1)

    try:
        return resp.json()
    except ValueError:
        print("错误：响应不是合法 JSON：{}".format(resp.text[:2000]))
        sys.exit(1)


def extract_text(resp_json: dict) -> str:
    """从 Anthropic Messages 响应的 content 分块中拼接纯文本。"""
    blocks = resp_json.get("content") or []
    return "".join(
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def normalize_tokens(model_name: str) -> list:
    """把模型名拆成小写 token：'.'、'-'、'_' 均视为分隔符。

    例如 "doubao-seed-2.0-lite" 与 "doubao-seed-2-0-lite-250815"
    分别拆为 ['doubao','seed','2','0','lite']
    和 ['doubao','seed','2','0','lite','250815']。
    """
    for sep in (".", "-", "_"):
        model_name = model_name.replace(sep, " ")
    return [tok.lower() for tok in model_name.split() if tok]


def compare_models(requested: str, served: str) -> str:
    """比较请求的模型与服务端实际返回的模型。

    返回三种判定：
      - "exact"        完全一致；
      - "same_family"  服务端返回的是同一模型，仅多了纯数字的版本/日期
                      快照后缀（如 doubao-seed-2-0-lite-250815）；
      - "mismatch"     不是同一个模型（可能被路由/回退到了其他模型）。
    """
    if served == requested:
        return "exact"

    req_tokens = normalize_tokens(requested)
    served_tokens = normalize_tokens(served)
    # 服务端名以请求名的全部 token 为前缀，且多余 token 全为纯数字
    # （日期快照 / 版本号 / 上下文规格，如 250815、204800），视为同模型。
    if (len(served_tokens) > len(req_tokens)
            and served_tokens[:len(req_tokens)] == req_tokens
            and all(tok.isdigit() for tok in served_tokens[len(req_tokens):])):
        return "same_family"
    return "mismatch"


def main() -> None:
    api_key = load_api_key()
    resp_json = send_message(api_key)

    answer = extract_text(resp_json)
    print("\n--- 模型回答 ---")
    print(answer if answer else "（未返回文本内容）")

    usage = resp_json.get("usage") or {}
    if usage:
        print("--- Token 用量（可用于对照套餐额度扣减）---")
        print("input_tokens={}, output_tokens={}".format(
            usage.get("input_tokens"), usage.get("output_tokens")))

    # ===== 核心：核对模型 =====
    served_model = resp_json.get("model")
    print("\n--- 模型核对 ---")
    print("我请求的模型       : {}".format(REQUESTED_MODEL))
    print("服务端实际回给我的模型: {}".format(served_model if served_model else "（响应中缺失 model 字段！）"))

    if not served_model:
        print("🚨 报警：响应中没有 model 字段，无法核对实际服务模型，请人工排查！")
        sys.exit(2)

    verdict = compare_models(REQUESTED_MODEL, served_model)
    if verdict == "exact":
        print("✅ 核对通过：实际服务模型与请求模型完全一致。")
    elif verdict == "same_family":
        # 同一模型、服务端返回了带版本快照后缀的具体名，不构成被换模型的风险，
        # 但差异明确展示出来，便于你按需做更严格的字面校验。
        print("✅ 核对通过：实际服务模型与请求模型为同一模型"
              "（服务端返回了带版本/日期后缀的具体模型名，前缀与请求模型一致）。")
    else:
        print("🚨🚨🚨 报警：模型不一致！🚨🚨🚨")
        print("🚨 请求的是 {}，但服务端实际服务的是 {}。".format(REQUESTED_MODEL, served_model))
        print("🚨 两个模型的套餐抵扣系数可能相差数倍，请立即排查"
              "（确认模型名拼写、套餐内模型清单，或联系火山方舟）。")
        sys.exit(2)


if __name__ == "__main__":
    main()
