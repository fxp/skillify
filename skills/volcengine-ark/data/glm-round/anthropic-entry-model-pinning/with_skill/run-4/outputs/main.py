#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan（个人版）· Anthropic 协议入口 · 单次对话 + 模型一致性核对。

场景：成本敏感。套餐内各模型 AFP 抵扣系数差达 40 倍（doubao-seed-2.0-mini 0.25 ~
kimi-k3 10），且方舟 Anthropic 入口会把 `claude-*` 之类的模型名**静默路由**到
doubao-seed-2.1-turbo（系数 2.5）而不报错。因此本脚本显式请求
`doubao-seed-2.0-lite`（系数 0.5），并在响应回来后核对服务端实际服务的模型，
不一致立刻报警并以非零码退出。

接入要点（与方舟其他入口互不通用）：
  - Base URL：https://ark.cn-beijing.volces.com/api/plan（Anthropic 协议，
    Messages 全路径 POST /api/plan/v1/messages）。不要用 /api/v3（后付费）或
    /api/coding（Coding Plan），Agent Plan 专属 Key 打这两个入口直接 401。
  - 鉴权：Agent Plan 专属 API Key（环境变量 ARK_AGENT_PLAN_API_KEY）。
    Anthropic 头写法 x-api-key 与 Authorization: Bearer 实测均被接受。
  - model 填 Model Name（点号、不带日期）：doubao-seed-2.0-lite。
  - 响应为标准 Anthropic Message 对象；注意响应里的 model 字段是 Plan 入口
    解析后的具体版本 ID（如 doubao-seed-2-0-lite-260215），不会与请求的
    Model Name 逐字相等，比对需先归一化（见 normalize_model_name）。

退出码：0 = 请求成功且模型一致；1 = 模型不一致（已报警）；2 = 环境或请求出错。
"""

import os
import re
import sys

import requests

# ---- Agent Plan 专属配置 ------------------------------------------------------
MESSAGES_URL = "https://ark.cn-beijing.volces.com/api/plan/v1/messages"
API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

REQUESTED_MODEL = "doubao-seed-2.0-lite"  # Model Name（点号、无日期）；AFP 系数 0.5

# Agent Plan 内文本模型的 AFP 抵扣系数（输入=输出），用于成本侧打印
AFP_COEFFICIENTS = {
    "doubao-seed-2-0-mini": 0.25,
    "doubao-seed-2-0-lite": 0.5,
    "deepseek-v4-flash": 0.5,
    "glm-5-3-flash": 0.5,
    "doubao-seed-2-1-turbo": 2.5,
    "doubao-seed-evolving": 2.5,
    "minimax-m3": 2.5,
    "glm-5-3": 4.5,
    "kimi-k2-7-code": 4.5,
    "deepseek-v4-pro": 5.5,
    "kimi-k3": 10.0,
}


def normalize_model_name(name):
    """把请求的 Model Name 与响应的 Model ID 归一化到同一形态再比对。

    Plan 入口会把 `doubao-seed-2.0-lite` 解析成 `doubao-seed-2-0-lite-260215`
    （点号转连字符，并带上日期版本后缀，且版本号不受理户端控制）。因此：
      1) 小写；2) 点号转连字符；3) 去掉结尾的 6 位日期版本号。
    例：doubao-seed-2.0-lite / doubao-seed-2-0-lite-260215 -> doubao-seed-2-0-lite
    而被静默路由到 doubao-seed-2-1-turbo-260628 时归一化为 doubao-seed-2-1-turbo，
    与请求不符，触发报警。
    """
    name = (name or "").strip().lower()
    name = name.replace(".", "-")
    name = re.sub(r"-\d{6}$", "", name)
    return name


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(
            f"[错误] 未设置环境变量 {API_KEY_ENV}。"
            "请在 Agent Plan 控制台「使用配置 → 配置专属API Key」获取 Key 后 "
            f"export {API_KEY_ENV}=<你的Key> 再运行。",
            file=sys.stderr,
        )
        return 2

    headers = {
        "x-api-key": api_key,  # Anthropic 协议原生鉴权头；Authorization: Bearer 亦可
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": 1024,  # Anthropic 协议必填；一句话回答绰绰有余
        # doubao-seed-2.0-lite 默认开深度思考，思维链按输出 token 计 AFP；
        # 关闭思考已实测被该模型接受（glm-5.3 等不支持此参数，换模型时需去掉）
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
    }

    try:
        resp = requests.post(MESSAGES_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"[错误] 请求失败：{exc}", file=sys.stderr)
        return 2

    if resp.status_code != 200:
        print(f"[错误] HTTP {resp.status_code}，响应原文：\n{resp.text[:2000]}", file=sys.stderr)
        if resp.status_code == 401:
            print("提示：401 通常是把 Agent Plan 专属 Key 打到了 /api/v3 或 /api/coding，"
                  "或 Key 本身无效。Agent Plan 只能用 /api/plan 入口 + 专属 Key。", file=sys.stderr)
        elif resp.status_code == 404:
            print("提示：404 UnsupportedModel 表示该模型不在当前套餐档位内"
                  "（如 Medium 档无 kimi-k3 以外的部分模型、视频模型）。", file=sys.stderr)
        return 2

    try:
        data = resp.json()
    except ValueError:
        print(f"[错误] 响应不是合法 JSON：{resp.text[:2000]}", file=sys.stderr)
        return 2

    served_model = data.get("model", "")
    # content 是 block 数组：开思考时混有 {"type":"thinking"}，只取 text block
    answer = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ).strip()
    usage = data.get("usage", {})

    # ---- 模型一致性核对（本脚本的核心） ----
    req_norm = normalize_model_name(REQUESTED_MODEL)
    srv_norm = normalize_model_name(served_model)
    matched = bool(served_model) and srv_norm == req_norm

    print("=" * 62)
    print(f"我请求的模型         : {REQUESTED_MODEL}")
    print(f"服务端实际回的模型   : {served_model or '<响应中缺失 model 字段>'}")
    print(f"归一化比对           : {req_norm}  vs  {srv_norm or '<空>'}")
    coeff = AFP_COEFFICIENTS.get(srv_norm)
    if coeff is not None:
        print(f"实际服务模型 AFP 系数: {coeff:g}（请求目标 doubao-seed-2.0-lite 为 0.5）")
    print("=" * 62)
    print(f"回答：{answer}")
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    if in_tok is not None or out_tok is not None:
        est = ""
        if coeff is not None and in_tok is not None and out_tok is not None:
            est = f"，约 {(in_tok + out_tok) * coeff / 10000:.4f} AFP"
        print(f"用量：input_tokens={in_tok}, output_tokens={out_tok}{est}")

    if matched:
        print("[通过] 服务端实际服务的模型与请求一致（日期后缀是 Plan 入口的版本解析，属正常）。")
        return 0

    # 不一致：明确报警
    print(
        "\n" + "!" * 62 +
        f"\n[报警] 模型不一致！请求的是 {REQUESTED_MODEL}，实际服务的是 "
        f"{served_model or '<缺失>'}。"
        "\n        这意味着 AFP 正在按别的模型的系数抵扣（如 claude-* 被静默路由到"
        "\n        doubao-seed-2.1-turbo，系数 2.5，是 lite 的 5 倍），请立即排查配置。"
        "\n" + "!" * 62,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
