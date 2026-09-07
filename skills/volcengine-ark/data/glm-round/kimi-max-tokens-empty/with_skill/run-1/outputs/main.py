#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan · kimi-k3 情感分类。

用法：
    export ARK_AGENT_PLAN_API_KEY=<Agent Plan 专属 API Key>
    python3 main.py            # 依赖：pip install requests

设计要点（依据 volcengine-ark 技能 2026-09-04 的真实 API 验证 + 官方文档）：
- 入口必须是 Agent Plan 专属 Base URL https://ark.cn-beijing.volces.com/api/plan/v3，
  Key 用 ARK_AGENT_PLAN_API_KEY（与方舟 API Key 不通用，打 /api/v3 会 401）。
- model 填小写 Model Name "kimi-k3"（Plan 入口不认带日期的 Model ID）。
- kimi-k3 默认开思考，且它的 max_tokens 实测把思维链也算在限额内：
  max_tokens=64 会 finish_reason="length"、content=""（思维链吃光额度、回答被截空）。
  因此逐级尝试：先 thinking disabled + max_tokens=64，力争把输出上限压在 64 以内；
  拿不到回答再退到 max_completion_tokens=400（限制"思维链+回答"总量，实测能拿到回答；
  上限只是天花板，计费按实际生成的 token 算，上限设大不等于多花钱）。
- max_tokens 与 max_completion_tokens 官方规定不可同时传，两个方案各自只带其一。

退出码：0 = 拿到分类结果；1 = 没拿到（会打印每次尝试的具体原因）；2 = 未配置 Key。
"""

import json
import os
import sys

import requests

API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
MODEL = "kimi-k3"
TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")
PROMPT = (
    "对下面这句评论做情感分类，只输出「正面」「负面」「中性」三个词中的一个，"
    "不要输出解释、标点或任何其他文字。\n评论：" + TEXT
)
TIMEOUT = 300  # 思考类模型的非流式响应偏慢，给足余量

# 逐级尝试：优先满足"输出上限压到 64 token 以内"，拿不到结果再放宽。
ATTEMPTS = (
    {
        "name": "尝试1 max_tokens=64 + thinking=disabled",
        "extra": {"max_tokens": 64, "thinking": {"type": "disabled"}},
    },
    {
        "name": "尝试2 max_completion_tokens=400",
        "extra": {"max_completion_tokens": 400},
    },
)


def extract_label(text):
    """从模型回答中提取三个标签之一；提取不到返回 None，绝不猜、绝不过关。"""
    t = (text or "").strip()
    if t in LABELS:
        return t
    for label in LABELS:
        if label in t:
            return label
    return None


def describe_error_body(body):
    """把错误响应压缩成一行可读文本。"""
    try:
        err = json.loads(body).get("error") or {}
        if isinstance(err, dict):
            code, msg = err.get("code", ""), err.get("message", "")
            if code or msg:
                return "{}: {}".format(code, msg)
        return (body or "")[:200]
    except (ValueError, AttributeError):
        return (body or "")[:200]


def call_model(api_key, extra_params):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    payload.update(extra_params)
    return requests.post(
        API_URL,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print(
            "[错误] 未设置环境变量 ARK_AGENT_PLAN_API_KEY。"
            "请在 Agent Plan 控制台第 3 步「配置专属API Key」获取（与方舟 API Key 不通用）。",
            file=sys.stderr,
        )
        return 2

    failures = []
    for attempt in ATTEMPTS:
        print("—— {} ——".format(attempt["name"]))
        try:
            resp = call_model(api_key, attempt["extra"])
        except requests.RequestException as exc:
            reason = "{}: 请求异常 {!r}".format(attempt["name"], exc)
            failures.append(reason)
            print("[未成功] " + reason)
            continue

        if resp.status_code != 200:
            reason = "{}: HTTP {} {}".format(
                attempt["name"], resp.status_code, describe_error_body(resp.text)
            )
            failures.append(reason)
            print("[未成功] " + reason)
            continue

        try:
            data = resp.json()
        except ValueError:
            reason = "{}: 响应不是合法 JSON: {!r}".format(attempt["name"], resp.text[:300])
            failures.append(reason)
            print("[未成功] " + reason)
            continue

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage") or {}
        reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        completion_tokens = usage.get("completion_tokens")
        print(
            "finish_reason={}, completion_tokens={}（其中思维链 {}），回答原文={!r}".format(
                finish_reason, completion_tokens, reasoning_tokens, content
            )
        )

        label = extract_label(content)
        if label:
            print()
            print("情感分类结果：" + label)
            answer_tokens = None
            if isinstance(completion_tokens, int) and isinstance(reasoning_tokens, int):
                answer_tokens = completion_tokens - reasoning_tokens
            print(
                "（出自{}；本次实际输出 {} token，其中思维链 {}、回答本体 {} token）".format(
                    attempt["name"], completion_tokens, reasoning_tokens, answer_tokens
                )
            )
            if "max_completion_tokens" in attempt["extra"]:
                print(
                    "说明：64 token 的输出上限在 kimi-k3 上无法与\"拿到结果\"同时满足——"
                    "它默认开思考且思维链计入 max_tokens，64 的额度会被思维链吃光、回答被截空；"
                    "本方案把上限放宽到 400（思维链+回答共用），回答本体本身只有几个 token。"
                )
            return 0

        if not content.strip():
            reason = (
                "{}: 回答为空（finish_reason={}, completion_tokens={}, 其中思维链 {}）"
                "——token 上限被思维链耗尽，回答被截空".format(
                    attempt["name"], finish_reason, completion_tokens, reasoning_tokens
                )
            )
        else:
            reason = "{}: 回答中不含三个标签之一，原文 {!r}".format(attempt["name"], content)
        failures.append(reason)
        print("[未成功] " + reason)

    print()
    print("[最终结论] 没有拿到分类结果，不输出空结果。各次尝试的具体原因：")
    for reason in failures:
        print("  - " + reason)
    print(
        "排查建议：1) ARK_AGENT_PLAN_API_KEY 必须是 Agent Plan 专属 Key（方舟 API Key 打这个入口会 401）；"
        "2) kimi-k3 需要 Medium 及以上档位（Small 档不可用，会 404 UnsupportedModel）；"
        "3) 确认 5 小时/周/月额度未耗尽（kimi-k3 不支持超额后付费）。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
