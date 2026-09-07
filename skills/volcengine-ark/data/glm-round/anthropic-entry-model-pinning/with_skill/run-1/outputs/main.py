#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan（个人版 Medium）· Anthropic 协议入口 —— 一次对话请求 + 模型钉扎核对

用法:
    export ARK_AGENT_PLAN_API_KEY=<Agent Plan 专属 API Key>   # 注意不是方舟 API Key
    python3 main.py

做什么:
    1. 用 Anthropic 协议入口 POST /api/plan/v1/messages 问一句「用一句话介绍 Python」;
    2. 打印「我请求的模型」与「服务端实际回给我的模型」（响应体里的 model 字段）;
    3. 归一化到模型家族后比对，不一致立刻报警并以非零码退出。

为什么核对不能做裸字符串相等（实测 2026-09-04，Agent Plan Medium）:
    - Plan 入口会把点分 Model Name `doubao-seed-2.0-lite` 解析到固定日期版本，
      响应 model 回显 `doubao-seed-2-0-lite-260215`，逐字比较永远不相等；
    - 反过来，Anthropic 入口传任何 `claude-*` 模型名会被【静默路由】到
      `doubao-seed-2-1-turbo-260628`（HTTP 200，不报错），AFP 抵扣系数 2.5，
      是 lite（0.5）的 5 倍。所以本脚本只显式请求 doubao-seed-2.0-lite，
      并在响应回来后核验服务端真的用了 lite 家族，别的模型一律报警。
"""

import json
import os
import re
import sys

import requests

# ---- 入口与鉴权（Agent Plan 专属，勿改） --------------------------------
# Anthropic 协议 Base URL 是 /api/plan，Messages 全路径 /api/plan/v1/messages。
# 拿这把专属 Key 打 /api/v3 或 /api/coding/v3 会直接 401，不会静默扣费。
ANTHROPIC_MESSAGES_URL = "https://ark.cn-beijing.volces.com/api/plan/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
TIMEOUT_SECONDS = 60

# ---- 必须钉死的模型 ------------------------------------------------------
# 只能填套餐内 Model Name（点分、小写、不带日期）。绝不能写 claude-*（会被静默
# 换成 doubao-seed-2-1-turbo），也不要写带日期的 Model ID（版本号会被静默忽略）。
REQUESTED_MODEL = "doubao-seed-2.0-lite"
MAX_TOKENS = 512          # Anthropic 协议必填；关了思考后 512 对一句话绰绰有余
QUESTION = "用一句话介绍 Python"

# 归一化时剥离的日期版本后缀：Model ID 固定以 6 位数字结尾，如 -260215 / -260428
_DATE_SUFFIX_RE = re.compile(r"-\d{6}$")


def normalize_model_name(name):
    """把请求名 / 回显名归一化成「模型家族」再比较。

    规则: 小写 -> 点换成连字符 -> 剥掉结尾的 6 位日期版本段。
    例: doubao-seed-2.0-lite          -> doubao-seed-2-0-lite
        doubao-seed-2-0-lite-260215   -> doubao-seed-2-0-lite
        doubao-seed-2-1-turbo-260628  -> doubao-seed-2-1-turbo
    Name->版本的映射由方舟侧维护、随时可能变，所以只比家族、不比日期。
    """
    n = (name or "").strip().lower().replace(".", "-")
    return _DATE_SUFFIX_RE.sub("", n)


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def extract_text(content):
    """从 Anthropic content block 数组里拼出回答文本（只取 text block）。"""
    if not isinstance(content, list):
        return ""
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def print_api_error(status_code, body_text):
    """按方舟错误结构打印非 2xx 响应；判别用 error.code（type 可能为空串）。"""
    print("\n[失败] HTTP %s" % status_code, file=sys.stderr)
    body_text = (body_text or "").strip()
    if not body_text:
        # Plan 入口部分 404 的 body 为空，先判空再解析
        print("响应 body 为空（endpoint 可能不存在）。", file=sys.stderr)
        return
    try:
        err = json.loads(body_text).get("error") or {}
    except ValueError:
        print("响应 body 不是 JSON: %s" % body_text[:500], file=sys.stderr)
        return
    print("错误码   : %s" % err.get("code", "<unknown>"), file=sys.stderr)
    print("错误信息 : %s" % err.get("message", "<unknown>"), file=sys.stderr)
    if err.get("param"):
        print("出错参数 : %s" % err["param"], file=sys.stderr)


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        die("[失败] 未设置环境变量 %s。\n"
            "请在 Agent Plan 控制台「使用配置 -> 配置专属API Key」获取专属 Key 后:\n"
            "  export %s=<你的 Agent Plan 专属 Key>" % (API_KEY_ENV, API_KEY_ENV))

    # 显式关闭思考: doubao-seed-2.0-lite 默认开思考，thinking.type=disabled 实测生效，
    # 可省掉思维链 token 的 AFP 抵扣。
    payload = {
        "model": REQUESTED_MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": QUESTION}],  # role 只认 system/user/assistant/tool
    }
    headers = {
        "x-api-key": api_key,              # Anthropic 风格头，实测该入口接受；等价于 Authorization: Bearer
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }

    print("请求入口 : POST %s" % ANTHROPIC_MESSAGES_URL)
    print("问题     : %s" % QUESTION)
    print("-" * 72)

    try:
        resp = requests.post(ANTHROPIC_MESSAGES_URL, headers=headers,
                             json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        die("[失败] 网络请求异常: %s" % exc)

    if resp.status_code != 200:
        print_api_error(resp.status_code, resp.text)
        die("[提示] 常见原因: Key 用错(401 AuthenticationError，专属 Key 只在 /api/plan* 有效)、\n"
            "       模型不在套餐内(404 UnsupportedModel)、额度耗尽(429 QuotaExceeded)。")

    try:
        data = resp.json()
    except ValueError:
        die("[失败] 响应不是 JSON: %s" % resp.text[:500])

    served_model = data.get("model")
    if not served_model:
        die("[失败] 响应里没有 model 字段，无法核对实际服务的模型: %s" % json.dumps(data, ensure_ascii=False)[:500])

    answer = extract_text(data.get("content"))
    usage = data.get("usage") or {}

    # ---- 模型钉扎核对 ----
    expected_family = normalize_model_name(REQUESTED_MODEL)
    served_family = normalize_model_name(served_model)
    matched = (served_family == expected_family)

    print("回答     : %s" % (answer or "<无 text block>"))
    print("stop_reason: %s    usage: input=%s output=%s" % (
        data.get("stop_reason"), usage.get("input_tokens"), usage.get("output_tokens")))
    print("-" * 72)
    print("我请求的模型        : %s" % REQUESTED_MODEL)
    print("服务端实际回给我的模型: %s" % served_model)
    print("归一化后比对        : 期望家族=%s  实际家族=%s" % (expected_family, served_family))

    if matched:
        print("[OK] 模型核对一致：服务端确实用的是 %s 家族（Plan 入口会把点分 Name 解析成带日期的"
              "固定版本回显，属正常现象）。" % expected_family)
    else:
        print(
            "\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "!!  [报警] 实际服务的模型与请求的模型不一致！                   !!\n"
            "!!                                                            !!\n"
            "!!  请求的模型   : %s\n"
            "!!  实际服务的模型: %s\n"
            "!!  期望家族     : %s\n"
            "!!  实际家族     : %s\n"
            "!!                                                            !!\n"
            "!!  成本影响: 套餐内各模型 AFP 抵扣系数差好几倍               !!\n"
            "!!  （mini 0.25 / lite 0.5 / turbo 2.5 / glm-5.3 4.5 /        !!\n"
            "!!   kimi-k3 10）。本脚本只请求了 lite，被路由到别的模型       !!\n"
            "!!  意味着额度正按更高系数被消耗。                             !!\n"
            "!!                                                            !!\n"
            "!!  排查: 若实际家族是 doubao-seed-2-1-turbo，多半是请求里带了  !!\n"
            "!!  claude-* 模型名被 Anthropic 入口静默路由（HTTP 仍 200）。   !!\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            % (REQUESTED_MODEL, served_model, expected_family, served_family),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
