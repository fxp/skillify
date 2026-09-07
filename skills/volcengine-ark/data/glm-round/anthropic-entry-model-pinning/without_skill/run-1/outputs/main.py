#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan（个人版 Medium）· Anthropic 协议入口 · 一次性对话 + 模型钉死核对。

背景：
    Agent Plan 按模型类别扣减 AFP，不同模型抵扣系数差好几倍
    （lite 档远低于 pro / kimi / glm / deepseek 档，具体以官方
    《套餐内 AFP 抵扣规则》为准）。因此本脚本把模型钉死为
    doubao-seed-2.0-lite，并在响应中核对服务端实际服务的模型，
    一旦被换成其它模型立即报警。

接口要点（官方文档「Agent Plan 个人版 → 接入 AI 工具 → Claude Code」）：
    * Anthropic 协议兼容入口给 Claude Code 的配置是
      ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/plan，
      Anthropic Messages 协议在其后拼接 /v1/messages；
      另有镜像写法 https://ark.cn-beijing.volces.com/api/plan/v3/anthropic
      （对应标准 API 的 /api/v3/anthropic 风格）。本脚本优先用前者，
      仅当前者返回 404（路径不存在）时才改试后者。
    * 必须使用 Agent Plan 专用 API Key（与普通按量 API Key 不通用）。
    * model 直接填套餐内模型 ID，官方写法为点号、无日期后缀：
      doubao-seed-2.0-lite。不要用 ark-code-latest 之类的路由别名，
      那会让方舟自行决定实际服务模型。

用法：
    export ARK_AGENT_PLAN_API_KEY="<你的 Agent Plan 专用 API Key>"
    python3 main.py

退出码：0 = 成功且模型一致；1 = 模型不一致（或无法核对）；2 = 请求/配置出错。
"""

import json
import os
import re
import sys

import requests

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

# 成本敏感：只允许这个模型服务本次请求，绝不让服务端自行路由。
REQUESTED_MODEL = "doubao-seed-2.0-lite"

QUESTION = "用一句话介绍 Python"
MAX_TOKENS = 512  # Anthropic Messages 协议必填参数
TIMEOUT_SECONDS = 60
ANTHROPIC_VERSION = "2023-06-01"

MESSAGES_URLS = [
    # 官方给 Claude Code 的 Base URL 为 https://ark.cn-beijing.volces.com/api/plan，
    # Anthropic 协议在其后拼 /v1/messages：
    "https://ark.cn-beijing.volces.com/api/plan/v1/messages",
    # 镜像写法（/api/v3/anthropic 风格），仅在上一条 404 时尝试：
    "https://ark.cn-beijing.volces.com/api/plan/v3/anthropic/v1/messages",
]


def canonical_model_name(name):
    """归一化模型名用于容错比对。

    规则：去首尾空白、转小写、'.' 视同 '-'、去掉结尾的 6 位日期版本号（-YYMMDD）。
    这样 doubao-seed-2.0-lite / doubao-seed-2-0-lite / doubao-seed-2-0-lite-250902
    都视为同一个模型；而 doubao-seed-2.0-pro、kimi-k3 等其它模型仍判为不一致。
    """
    normalized = name.strip().lower().replace(".", "-")
    return re.sub(r"-\d{6}$", "", normalized)


def send_request(api_key):
    """向 Anthropic 协议入口发一次对话请求，返回 requests.Response（失败返回 None）。"""
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "Authorization": "Bearer " + api_key,  # Claude Code（ANTHROPIC_AUTH_TOKEN）的鉴权方式
        "x-api-key": api_key,  # Anthropic 协议标准鉴权头，一并带上双保险
    }
    payload = {
        "model": REQUESTED_MODEL,  # 显式钉死模型，不用路由别名
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": QUESTION}],
    }

    for index, url in enumerate(MESSAGES_URLS):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            print("错误：请求 %s 失败：%s" % (url, exc), file=sys.stderr)
            return None
        if resp.status_code == 404 and index < len(MESSAGES_URLS) - 1:
            # 404 说明该路径不存在（模型 ID 写错时也可能 404，
            # 届时最终错误信息里会带上响应体，可据其判断）。
            print("提示：%s 返回 404，改试备用入口……" % url)
            continue
        return resp
    return None


def extract_answer_text(data):
    """从 Anthropic Messages 响应里取出全部 text 块拼接成回复文本。"""
    blocks = data.get("content") or []
    return "".join(
        block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def report_mismatch(served_model, data):
    """模型不一致：明确报警。"""
    print("", file=sys.stderr)
    print("🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨", file=sys.stderr)
    print("🚨 警报：服务端实际服务的模型与请求的不一致！", file=sys.stderr)
    print("🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨", file=sys.stderr)
    print("我请求的模型           : %s" % REQUESTED_MODEL, file=sys.stderr)
    print("服务端实际回给我的模型  : %s" % served_model, file=sys.stderr)
    print("实际服务的不是 doubao-seed-2.0-lite！Agent Plan 各模型抵扣系数差好几倍，", file=sys.stderr)
    print("请立刻停止放量并排查（检查是否误用了路由别名/入口，或套餐内模型调整）。", file=sys.stderr)
    print("原始响应：%s" % json.dumps(data, ensure_ascii=False), file=sys.stderr)


def main():
    print("=" * 64)
    print("火山方舟 Agent Plan · Anthropic 协议入口 · 模型钉死核对")
    print("=" * 64)
    print("我请求的模型          : %s" % REQUESTED_MODEL)
    print("问题                  : %s" % QUESTION)
    print("-" * 64)

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print("错误：未设置环境变量 %s（需为 Agent Plan 专用 API Key）。" % API_KEY_ENV, file=sys.stderr)
        print("请先执行：export %s=<你的 Key>" % API_KEY_ENV, file=sys.stderr)
        return 2

    resp = send_request(api_key)
    if resp is None:
        return 2
    if resp.status_code != 200:
        print("错误：HTTP %d" % resp.status_code, file=sys.stderr)
        print(resp.text, file=sys.stderr)
        return 2

    try:
        data = resp.json()
    except ValueError:
        print("错误：响应不是合法 JSON：\n%s" % resp.text, file=sys.stderr)
        return 2

    served_model = (data.get("model") or "").strip()
    answer = extract_answer_text(data)
    usage = data.get("usage") or {}

    print("模型回复              : %s" % (answer or "（空）"))
    if usage:
        print(
            "Token 用量            : 输入 %s / 输出 %s"
            % (usage.get("input_tokens", "?"), usage.get("output_tokens", "?"))
        )
    print("-" * 64)
    print("我请求的模型          : %s" % REQUESTED_MODEL)
    print("服务端实际回给我的模型 : %s" % (served_model or "（响应中无 model 字段）"))

    if not served_model:
        # 没有 model 字段就无法核对，按最坏情况处理。
        print("", file=sys.stderr)
        print("🚨 警报：响应中没有 model 字段，无法核对实际服务的模型！", file=sys.stderr)
        print("原始响应：%s" % json.dumps(data, ensure_ascii=False), file=sys.stderr)
        return 1

    if served_model == REQUESTED_MODEL:
        print("核对结果：✅ 一致，本次请求确实由 %s 服务。" % REQUESTED_MODEL)
        return 0
    if canonical_model_name(served_model) == canonical_model_name(REQUESTED_MODEL):
        print("核对结果：✅ 一致（服务端返回的是同一模型的另一写法/带日期版本号）。")
        return 0

    report_mismatch(served_model, data)
    return 1


if __name__ == "__main__":
    sys.exit(main())
