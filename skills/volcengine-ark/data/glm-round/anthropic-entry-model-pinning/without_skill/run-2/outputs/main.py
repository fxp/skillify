#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan（个人版 Medium）· Anthropic 协议入口 · 单次对话 + 模型钉死核对。

成本敏感场景：套餐内不同模型抵扣系数差数倍，本脚本把模型钉死为
doubao-seed-2.0-lite，并在响应返回后核对「服务端实际服务的模型」，
不一致时给出明确报警并以非零退出码结束。

接口依据（火山方舟官方文档 · Agent Plan 个人版）：
- Anthropic 协议专属 Base URL：https://ark.cn-beijing.volces.com/api/plan
  （文档明确：该 Base URL 为 Agent Plan 专属，其他 Base URL 无法在 Agent Plan 中使用；
   Messages 端点 = Base URL + /v1/messages，与 Claude Code 的调用方式一致）
- 鉴权：Agent Plan 专属 API Key（文档以 ANTHROPIC_AUTH_TOKEN 方式下发，
  即 Authorization: Bearer；同时附带 Anthropic 标准的 x-api-key 头以增强兼容性）
- doubao-seed-2.0-lite：文本生成（标准档），Small/Medium/Large/Max 套餐均支持。

⚠️ 合规提示：官方「套餐概览」写明：文本生成模型及向量化模型不可用于 API 调用，
在非 AI 工具中使用 Agent Plan 的 Base URL 和 API Key 有可能被识别为滥用/违规，
会导致订阅停用或账号封禁。本脚本建议仅用于一次性的模型核对验证，勿长期批量调用。

退出码约定：0 = 模型一致；1 = 模型不一致（已报警）；2 = 请求或配置本身失败。
"""

import json
import os
import sys

import requests

# Agent Plan 专属 Anthropic 协议 Base URL（注意：不是 /api/v3，也不是 Coding Plan 的 /api/coding）
ANTHROPIC_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
MESSAGES_PATH = "/v1/messages"

# 成本敏感：必须钉死为低价档的 doubao-seed-2.0-lite，不接受服务端换别的模型
REQUESTED_MODEL = "doubao-seed-2.0-lite"

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
TIMEOUT_SECONDS = 60
MAX_TOKENS = 1024  # Anthropic 协议必填；留足余量，防思考类模型挤占输出


def build_headers(api_key: str) -> dict:
    """Agent Plan 的 Anthropic 兼容入口鉴权头。

    官方文档以 ANTHROPIC_AUTH_TOKEN（Bearer）方式下发密钥；
    同时带 x-api-key（Anthropic 标准头），两种鉴权网关都能识别。
    """
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }


def extract_text(data: dict) -> str:
    """从 Anthropic Messages 响应的 content 数组里拼出纯文本回答。"""
    parts = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts).strip()


def norm(name: str) -> str:
    """比较用的归一化：仅去空白、统一小写（模型名本身全小写，不会误伤）。"""
    return (name or "").strip().lower()


def report_mismatch(requested: str, served: str) -> None:
    print("!" * 72, file=sys.stderr)
    print("[报警] 模型不一致：实际服务的模型不是所请求的 {}！".format(requested), file=sys.stderr)
    print("       我请求的模型        : {}".format(requested), file=sys.stderr)
    print("       服务端实际返回的模型: {}".format(served or "(响应中无 model 字段)"), file=sys.stderr)
    print("       该场景成本敏感，不同模型抵扣系数差数倍，请立即停止使用并排查：", file=sys.stderr)
    print("       - 是否误用了 Coding Plan / 方舟后付费的其他 Base URL 或 API Key；", file=sys.stderr)
    print("       - 是否被控制台侧的 Auto/路由模式改写了模型。", file=sys.stderr)
    print("!" * 72, file=sys.stderr)


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print("[错误] 未检测到环境变量 {}。".format(API_KEY_ENV), file=sys.stderr)
        print("请在 Agent Plan 控制台获取「专属 API Key」（与方舟平台/Coding Plan 的 Key 不通用），然后：", file=sys.stderr)
        print('  export {}="<你的 Agent Plan 专属 API Key>"'.format(API_KEY_ENV), file=sys.stderr)
        return 2

    url = ANTHROPIC_BASE_URL.rstrip("/") + MESSAGES_PATH
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Python"},
        ],
    }

    print("请求端点                              : {}".format(url))
    print("我请求的模型 (requested model)        : {}".format(REQUESTED_MODEL))
    print("-" * 72)

    try:
        resp = requests.post(url, headers=build_headers(api_key), json=payload, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as exc:
        print("[错误] 请求失败（网络/超时）：{}".format(exc), file=sys.stderr)
        return 2

    if resp.status_code != 200:
        print("[错误] HTTP {}，响应正文：".format(resp.status_code), file=sys.stderr)
        print(resp.text[:2000], file=sys.stderr)
        return 2

    try:
        data = resp.json()
    except ValueError:
        print("[错误] 响应不是合法 JSON：{}".format(resp.text[:2000]), file=sys.stderr)
        return 2

    answer = extract_text(data)
    usage = data.get("usage") or {}
    print("模型回答                              : {}".format(answer or "(空)"))
    if usage:
        print("用量                                  : {}".format(json.dumps(usage, ensure_ascii=False)))

    # 服务端实际服务的模型：以响应体 model 字段为准（原样打印，不做任何加工）
    served_model = data.get("model") or ""
    print("-" * 72)
    print("我请求的模型 (requested model)        : {}".format(REQUESTED_MODEL))
    print("服务端实际返回的模型 (served model)   : {}".format(served_model or "(响应中无 model 字段)"))

    if not served_model:
        report_mismatch(REQUESTED_MODEL, served_model)
        return 1
    if norm(served_model) != norm(REQUESTED_MODEL):
        # 严格全等比较：即使服务端返回带版本后缀等“近似”名称（如 xxx-250901）也视为不一致并报警，
        # 成本敏感场景宁误报、不漏报，交由人工确认。
        report_mismatch(REQUESTED_MODEL, served_model)
        return 1

    print("[通过] 两者一致，本次请求确由 {} 服务。".format(REQUESTED_MODEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
