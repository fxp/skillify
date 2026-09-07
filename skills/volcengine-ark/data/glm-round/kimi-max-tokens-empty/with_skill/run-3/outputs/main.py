#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan · kimi-k3 · 情感三分类。

为什么不能简单地 max_tokens=64(依据 volcengine-ark skill 2026-09-04 的真实 API 验证):
  kimi-k3 默认开启思考,而且它把思维链也算进 max_tokens 额度——
  max_tokens=64 时 finish_reason="length"、content=""(思维链先吃光 64,回答被截成空)。
  因此本脚本:
  1) 用 max_completion_tokens(思维链+回答的总上限;与 max_tokens 互斥,二者只能传一个);
  2) 先尝试关闭思考 / 压低 reasoning_effort,力争把总输出压进 64 token;
  3) 压不进去就逐级放宽上限,保证真的拿到分类结果,并把原因与实际 token 用量如实打印。

入口与鉴权:Agent Plan 专属 Base URL https://ark.cn-beijing.volces.com/api/plan/v3 +
专属 Key(环境变量 ARK_AGENT_PLAN_API_KEY)。不要改用 /api/v3(专属 Key 打它是 401,
官方也警告套餐用户用错入口会产生额外费用)。model 填小写 Model Name「kimi-k3」
(不带日期;Agent Plan 需 Medium 及以上档位,Small 档不可用)。

依赖:仅 requests。运行:python3 main.py
"""

import os
import sys

import requests

API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
MODEL = "kimi-k3"
TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")
TIMEOUT = 120  # 秒;思考模型非流式偶发较慢,留足余量

CAP_TARGET = 64         # 期望的输出上限(思维链+回答合计)
CAP_FALLBACK = 512      # 64 装不下思维链时的兜底(实测 400 即可让 kimi-k3 正常返回)
CAP_LAST_RESORT = 2048  # 最后兜底,防个别请求思维链较长

# 依次尝试的参数组合。每条都只含 max_completion_tokens,绝不与 max_tokens 同传(两者互斥);
# thinking 与 reasoning_effort 也不同时传(官方未说明同传时的优先级)。
ATTEMPTS = (
    ("关闭思考 + 总输出上限 64", {"thinking": {"type": "disabled"}, "max_completion_tokens": CAP_TARGET}),
    ("reasoning_effort=low + 总输出上限 64", {"reasoning_effort": "low", "max_completion_tokens": CAP_TARGET}),
    (f"reasoning_effort=low + 放宽上限 {CAP_FALLBACK}", {"reasoning_effort": "low", "max_completion_tokens": CAP_FALLBACK}),
    (f"默认思考 + 放宽上限 {CAP_LAST_RESORT}", {"max_completion_tokens": CAP_LAST_RESORT}),
)

PROMPT = (
    "任务:对下面的句子做情感分类。\n"
    "约束:只输出「正面」「负面」「中性」三个词之一;不要解释、不要标点、不要任何多余文字。\n"
    f"句子:{TEXT}"
)


def call_api(api_key, params):
    """发一次请求。成功返回 (data, None);失败返回 (None, 错误说明)。"""
    payload = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}]}
    payload.update(params)
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        return None, f"网络请求失败:{exc!r}"

    if resp.status_code != 200:
        code, message = "", (resp.text or "")[:300]
        try:
            err = resp.json().get("error", {})
            code, message = err.get("code", ""), err.get("message", "")
        except ValueError:
            pass
        return None, f"HTTP {resp.status_code} {code}:{message}"

    try:
        return resp.json(), None
    except ValueError:
        return None, f"响应不是合法 JSON:{(resp.text or '')[:300]}"


def parse_result(data):
    """解析响应 → (命中词, finish_reason, 总输出token, 思维链token, 原始回答)。"""
    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    completion = usage.get("completion_tokens") or 0
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    label = next((x for x in LABELS if x in content), None)
    return label, choice.get("finish_reason"), completion, reasoning, content


def report_failure(history):
    print("未能拿到分类结果。各次尝试:", file=sys.stderr)
    for desc, note in history:
        print(f"  - {desc} → {note}", file=sys.stderr)
    print(
        "排查建议:\n"
        "  * 401 AuthenticationError:Key 用错。Agent Plan 必须用控制台『配置专属 API Key』生成的专属 Key,\n"
        "    普通方舟 API Key(ARK_API_KEY)打 /api/plan/* 一律 401。\n"
        "  * 404 UnsupportedModel:kimi-k3 需要 Agent Plan Medium 及以上档位(Small 档不可用),或套餐/模型已失效。\n"
        "  * 429 / 额度类报错:5 小时/周/月额度耗尽(kimi-k3 不支持超额后付费)或触发限流,稍后再试。\n"
        "  * 400 提示 thinking / reasoning_effort 不被支持:属预期内,脚本已自动换下一种参数组合重试。",
        file=sys.stderr,
    )


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print(
            "错误:环境变量 ARK_AGENT_PLAN_API_KEY 未设置。\n"
            "请在 Agent Plan 控制台『配置专属 API Key』处生成专属 Key,然后:\n"
            "  export ARK_AGENT_PLAN_API_KEY=<你的专属Key>",
            file=sys.stderr,
        )
        return 1

    history = []  # (尝试说明, 未成功原因)
    for desc, params in ATTEMPTS:
        data, error = call_api(api_key, params)
        if error is not None:
            history.append((desc, error))
            # 400 视为"该参数组合被模型拒绝"(如 kimi-k3 不支持 thinking.disabled),换下一种;
            # 其他错误(401/404/429/5xx…)重试也没有意义,直接终止并报告。
            if not error.startswith("HTTP 400"):
                report_failure(history)
                return 1
            continue

        label, finish, completion, reasoning, content = parse_result(data)
        cap = params["max_completion_tokens"]

        if label is not None and finish != "length":
            print(f"情感分类结果:{label}")
            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens") or 0
            print(
                f"[调用详情] 模型={data.get('model', MODEL)};{desc};"
                f"finish_reason={finish};总输出 {completion} token(其中思维链 {reasoning} token);"
                f"max_completion_tokens={cap}"
            )
            print(
                f"[成本] 输入 {prompt_tokens} token + 输出 {completion} token;"
                f"kimi-k3 的 AFP 抵扣系数为 10/10,本次约消耗 {(prompt_tokens + completion) * 10 / 10000:.3f} AFP"
            )
            if history:
                print("[前序尝试(未成功)]")
                for h_desc, h_note in history:
                    print(f"  - {h_desc} → {h_note}")
            if cap > CAP_TARGET:
                print(
                    f"[说明] 未能把输出上限压到 64 token,原因是 kimi-k3 默认开启思考且思维链计入输出额度,\n"
                    f"       64 的额度会被思维链吃光、回答为空(实测 max_tokens=64 即返回空 content),\n"
                    f"       关思考/压低思考的尝试也未在该模型上生效(见上)。\n"
                    f"       已放宽到 max_completion_tokens={cap} 拿到结果;计费按实际输出 token({completion})而非上限。"
                )
            return 0

        if not content:
            note = f"回答为空(finish_reason={finish}):思维链 {reasoning} token 占满了 {cap} 的额度,回答被截空"
        elif finish == "length":
            note = f"触顶截断(finish_reason=length),已输出:{content[:20]}"
        else:
            note = f"回答不含任何候选词,原文:{content[:30]}"
        history.append((desc, note))

    report_failure(history)
    return 1


if __name__ == "__main__":
    sys.exit(main())
