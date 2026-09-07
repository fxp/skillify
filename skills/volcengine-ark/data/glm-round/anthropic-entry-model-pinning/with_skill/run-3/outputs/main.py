"""火山方舟 Agent Plan（个人版）· Anthropic 协议入口调用 doubao-seed-2.0-lite。

用 Agent Plan 专属 Key 走 Anthropic 兼容入口 POST /api/plan/v1/messages 发一次对话，
并核对「我请求的模型」与「服务端实际回给我的模型」（响应体 model 字段）。

两个已知坑（2026-09-04 真实 API 实测，见 volcengine-ark skill 验证记录）：
1. 该入口会把任何 claude-* 模型名静默路由到 doubao-seed-2.1-turbo（抵扣系数 2.5，
   是 lite 的 5 倍），返回 200 不报错——所以 model 必须显式写套餐内 Model Name。
2. Plan 入口会把 Model Name 解析成带日期的 Model ID 并在响应 model 里回显：
   doubao-seed-2.0-lite -> doubao-seed-2-0-lite-260215（点变连字符 + 日期后缀）。
   日期版本由方舟侧维护、随时可能换，因此核对不能用朴素字符串相等，
   也不能硬编码日期，而是做归一化后按「模型系列」比对。

注意：Agent Plan 文本模型官方口径「不可用于 API 调用」（使用条款限制，非接口限制，
技术上能调通）；本脚本仅做一次最小请求用于验证模型路由。
"""

import os
import re
import sys

import requests

# Agent Plan 的 Anthropic 协议 Base URL 是 /api/plan，Messages 全路径 /api/plan/v1/messages。
# 不能用 /api/v3 或 /api/coding（专属 Key 打这两个入口是 401，不会静默扣费）。
MESSAGES_URL = "https://ark.cn-beijing.volces.com/api/plan/v1/messages"
API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"  # Agent Plan 专属 Key，与方舟 API Key 不通用

# 套餐内 Model Name（小写、版本用点）。绝不能填 claude-*，会被静默换成 2.1-turbo。
REQUESTED_MODEL = "doubao-seed-2.0-lite"


def normalize_model_name(name):
    """把模型名归一化成「系列名」，用于请求名与回结名的比对。

    处理两处差异：
    - Model Name 用点（doubao-seed-2.0-lite），Model ID 用连字符（doubao-seed-2-0-lite）；
    - 回显的 Model ID 带日期后缀（-260215），日期由方舟维护随时可能变，须忽略。
    同系列不同日期版本视为一致；跨系列（turbo/mini/glm/auto...）视为不一致。
    """
    n = (name or "").strip().lower().replace(".", "-")
    return re.sub(r"-\d{6}$", "", n)


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"错误：未设置环境变量 {API_KEY_ENV}（Agent Plan 专属 API Key）")

    headers = {
        # 实测 x-api-key 与 Authorization: Bearer 两种头均被接受，这里用 Anthropic 原生写法
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        # lite 默认开思考，思维链按输出 token 计 AFP；成本敏感场景显式关闭（实测该入口生效）
        "thinking": {"type": "disabled"},
    }

    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        sys.exit(f"错误：请求失败：{e}")

    if resp.status_code != 200:
        # 常见错误：401 = Key/入口不配套；404 UnsupportedModel = model 不是套餐内 Model Name
        print(f"请求失败：HTTP {resp.status_code}")
        print(resp.text[:2000])
        sys.exit(1)

    data = resp.json()
    served_model = data.get("model") or ""
    text = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    )
    usage = data.get("usage", {})

    print("=== 模型核对 ===")
    print(f"我请求的模型:         {REQUESTED_MODEL}")
    print(f"服务端实际回给我的模型: {served_model}")
    print()
    print(f"回答: {text}")
    if usage:
        print(
            f"用量: input_tokens={usage.get('input_tokens')}, "
            f"output_tokens={usage.get('output_tokens')}, "
            f"cache_read_input_tokens={usage.get('cache_read_input_tokens')}"
        )

    requested_norm = normalize_model_name(REQUESTED_MODEL)
    served_norm = normalize_model_name(served_model)
    if served_norm == requested_norm:
        print()
        print(f"核对通过：实际服务的是 {REQUESTED_MODEL} 系列（回显 {served_model}）。")
    else:
        print()
        print("=" * 60)
        print("⚠️  报警：模型不一致！")
        print(f"⚠️  我请求的是 {REQUESTED_MODEL}，但服务端实际服务的是 {served_model}")
        print("⚠️  套餐内不同模型 AFP 抵扣系数差好几倍（lite 0.5 / turbo 2.5 / glm-5.3 4.5 / kimi-k3 10），")
        print("⚠️  继续使用会按错误模型的系数扣减额度，请立即停止并检查 model 配置。")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
