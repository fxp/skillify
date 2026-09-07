#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用火山方舟 Agent Plan（个人版 Medium）的 Anthropic 协议入口发一次对话请求，
并核对「实际服务我的模型」是否真的是 doubao-seed-2.0-lite。

为什么必须核对（两个已由真实 API 验证的坑）：
1. Agent Plan 的 Anthropic 协议入口是 https://ark.cn-beijing.volces.com/api/plan
   （Messages 全路径 /api/plan/v1/messages），鉴权用 Agent Plan 专属 Key
   （环境变量 ARK_AGENT_PLAN_API_KEY）。这把 Key 打 /api/v3、/api/coding* 一律 401。
2. 该入口会静默改写 model：请求 doubao-seed-2.0-lite（Model Name，点号分隔），
   响应里的 model 是 doubao-seed-2-0-lite-260215（带日期的 Model ID，连字符）；
   更危险的是 claude-* 模型名会被静默路由到 doubao-seed-2-1-turbo-260628
   （AFP 系数 2.5，是 lite 0.5 的 5 倍），不报错、只悄悄多扣额度。
   所以不能只看请求参数，必须拿响应里的 model 字段反查实际服务的模型。

注意：官方口径 Agent Plan 的文本模型「不可用于 API 调用」（仅限 AI 编程工具内使用），
本脚本仅作单次连通性 / 模型核对用途，请勿高频调用。

用法：export ARK_AGENT_PLAN_API_KEY=... && python3 main.py
退出码：0 = 一致；1 = 请求失败；2 = 模型不一致（已报警）。
"""

import os
import re
import sys

import requests

# Agent Plan 专属 Anthropic 协议入口。
# 不要用 /api/v3（后付费入口）或 /api/plan/v3（那是 Agent Plan 的 OpenAI 协议入口）。
ANTHROPIC_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_URL = ANTHROPIC_BASE_URL + "/v1/messages"

# Plan 入口的 model 填不带日期的 Model Name（点号分隔）。带日期的 Model ID 也会被接受，
# 但版本号被静默忽略、无法锁版本，所以直接用 Model Name。
REQUESTED_MODEL = "doubao-seed-2.0-lite"

# 套餐内文本模型的 AFP 抵扣系数（输入=输出），仅用于不一致时给出成本提示；
# 系数可能随限时活动调整，以控制台为准。
AFP_COEFFICIENTS = {
    "doubao-seed-2.0-mini": 0.25,
    "doubao-seed-2.0-lite": 0.5,
    "deepseek-v4-flash": 0.5,
    "glm-5.3-flash": 0.5,
    "doubao-seed-2.1-turbo": 2.5,
    "doubao-seed-evolving": 2.5,
    "minimax-m3": 2.5,
    "glm-5.3": 4.5,
    "kimi-k2.7-code": 4.5,
    "deepseek-v4-pro": 5.5,
    "kimi-k3": 10.0,
}


def normalize_model(name):
    """把请求侧 Model Name 与响应侧 Model ID 归一成同一形态，用于一致性比对。

    doubao-seed-2.0-lite        -> doubao-seed-2-0-lite   （点号 -> 连字符）
    doubao-seed-2-0-lite-260215 -> doubao-seed-2-0-lite   （去掉 6 位日期版本后缀）
    glm-5.3                     -> glm-5-3                （第三方模型响应里保留点号）
    """
    n = name.strip().lower()
    n = re.sub(r"-\d{6}$", "", n)  # 去掉 -260215 这类日期后缀
    return n.replace(".", "-")


def lookup_coefficient(model_name):
    key = normalize_model(model_name)
    return next((v for k, v in AFP_COEFFICIENTS.items() if normalize_model(k) == key), None)


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        print("错误：请先设置环境变量 ARK_AGENT_PLAN_API_KEY"
              "（Agent Plan 专属 Key，在 Agent Plan 控制台「配置专属API Key」获取，与方舟 API Key 不通用）",
              file=sys.stderr)
        return 1

    headers = {
        "x-api-key": api_key,  # 实测 Authorization: Bearer 也可，二选一即可
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": 256,  # Anthropic 协议必填；一句话回答足够
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        # lite 默认开思考（一句话回答也可能烧上百思维链 token），显式关掉省钱；
        # 此写法在本入口对 doubao 系实测可用（glm-5.3 不支持 disabled，本脚本用的是 lite）。
        "thinking": {"type": "disabled"},
    }

    # 成本敏感：只发一次，不做重试（重试会重复扣 AFP）。
    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print("错误：请求失败（网络问题）：%s" % exc, file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print("错误：HTTP %d" % resp.status_code, file=sys.stderr)
        print(resp.text[:2000], file=sys.stderr)
        if resp.status_code == 401:
            print("提示：401 通常是 Key 或入口不对——Agent Plan 专属 Key 只在 /api/plan* 有效。",
                  file=sys.stderr)
        elif resp.status_code == 404:
            print("提示：404 UnsupportedModel 通常是该模型不在当前套餐档位内。", file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except ValueError:
        print("错误：响应不是合法 JSON：%s" % resp.text[:2000], file=sys.stderr)
        return 1

    actual_model = data.get("model", "")
    answer = "".join(block.get("text", "") for block in data.get("content", [])
                     if block.get("type") == "text").strip()
    usage = data.get("usage", {})

    print("回答：%s" % answer)
    print("请求的模型：%s" % REQUESTED_MODEL)
    print("服务端实际返回的模型：%s" % (actual_model or "<响应缺少 model 字段>"))
    if usage:
        print("token 用量：输入 %s，输出 %s"
              % (usage.get("input_tokens", "?"), usage.get("output_tokens", "?")))

    if not actual_model:
        print("警告：响应里没有 model 字段，无法核对实际服务的模型！", file=sys.stderr)
        return 2

    if normalize_model(actual_model) == normalize_model(REQUESTED_MODEL):
        print("[OK] 模型核对一致：实际服务的确实是 %s 系列"
              "（响应里带日期版本号，如 -260215，属该入口的正常现象）" % REQUESTED_MODEL)
        return 0

    # 不一致：明确报警
    req_coef = lookup_coefficient(REQUESTED_MODEL)
    act_coef = lookup_coefficient(actual_model)
    coef_note = ""
    if req_coef is not None and act_coef is not None and req_coef > 0:
        coef_note = ("\n  AFP 系数：请求 %s=%s，实际 %s=%s，相差 %.1f 倍"
                     % (REQUESTED_MODEL, req_coef, actual_model, act_coef, act_coef / req_coef))
    bar = "=" * 64
    print("\n%s\n【报警】实际服务的模型与请求不一致！\n"
          "  请求的模型：%s\n"
          "  实际的模型：%s%s\n"
          "  本次请求没有按预期模型服务/计费，请立即排查（常见原因：Anthropic 入口把 claude-* 名字"
          "静默路由到 doubao-seed-2.1-turbo，或请求被改写到了其他模型）。\n%s"
          % (bar, REQUESTED_MODEL, actual_model, coef_note, bar), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
