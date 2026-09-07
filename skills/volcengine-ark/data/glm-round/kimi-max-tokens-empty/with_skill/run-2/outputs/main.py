#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用火山方舟 Agent Plan 的 kimi-k3 做情感分类（只输出 正面/负面/中性 之一）。

为什么这个脚本要"先试 64、不行再放宽并如实报告"：
- kimi-k3 是思考模型，默认开思维链；实测（2026-09-04，Agent Plan Medium）它的
  max_tokens 把思维链算进上限：max_tokens=64 时 finish_reason="length"、
  content=""——思维链吃光预算（简单问题思维链就有 61 token），回答为空。
  直接压 64 必然拿到空结果。
- max_completion_tokens（上限=思维链+回答，不能与 max_tokens 同传）才是能拿到
  回答的写法，实测 400 可正常返回。
- kimi-k3 能否 thinking:{"type":"disabled"} 没有实测结论（glm-5.3 实测被 400
  拒绝，豆包系列可以）。所以先试"关思考 + max_tokens=64"这条唯一可能把总输出
  压进 64 token 的路；被拒或回答被截空时，退到 max_completion_tokens=512 并
  把"为什么 64 达不成"和实际 token 用量打印出来。

运行：export ARK_AGENT_PLAN_API_KEY=<Agent Plan 专属 Key> && python3 main.py
注：Agent Plan 官方口径"文本生成模型不可用于 API 调用"（使用条款限制，技术上
可调通），高频直调有被判滥用的风险；本脚本仅单次调用。
"""

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"  # Agent Plan 专属入口，勿用 /api/v3
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "kimi-k3"  # Plan 入口填小写 Model Name；Small 档不可用，需 Medium 及以上
TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")
REQUEST_TIMEOUT = 300  # 思考模型非流式调用可能较慢

# 思考模型建议少用 system、指令直接放 user（见方舟提示词工程建议）
MESSAGES = [
    {
        "role": "user",
        "content": (
            "任务：情感分类。判断下面这句话的情感倾向，答案只能是"
            "「正面」「负面」「中性」三个词之一，不要输出任何其他内容"
            "（不要标点、引号或解释）。\n"
            f"句子：{TEXT}"
        ),
    }
]

ATTEMPT_1 = {
    "name": "方案1：关闭思考 + max_tokens=64",
    "payload": {
        "model": MODEL,
        "messages": MESSAGES,
        "thinking": {"type": "disabled"},
        "max_tokens": 64,
    },
}

ATTEMPT_2 = {
    "name": "方案2：max_completion_tokens=512（上限含思维链）",
    "payload": {
        "model": MODEL,
        "messages": MESSAGES,
        "max_completion_tokens": 512,
    },
}


def call_api(api_key, payload):
    """POST /chat/completions。返回 (status_code, body_dict_or_None, 错误说明或_None)。"""
    try:
        resp = requests.post(
            CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return None, None, f"请求超时（>{REQUEST_TIMEOUT}s）。思考模型非流式调用可能很慢，可调大 timeout 或改流式。"
    except requests.exceptions.RequestException as exc:
        return None, None, f"网络错误：{exc}"

    try:
        body = resp.json()
    except ValueError:
        return resp.status_code, None, f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:300]}"
    return resp.status_code, body, None


def explain_http_error(status, body):
    """把常见失败码翻译成可操作的原因。"""
    err = (body or {}).get("error") or {}
    message = err.get("message", "")
    if status in (401, 403):
        return (
            "鉴权失败：ARK_AGENT_PLAN_API_KEY 无效，或它不是 Agent Plan 专属 Key。"
            "专属 Key 与方舟 API Key 不通用（专属 Key 打 /api/v3、/api/coding/v3 "
            "都会 401），请到 Agent Plan 控制台「使用配置 → 配置专属API Key」确认。"
        )
    if status == 404 and err.get("code") == "UnsupportedModel":
        return (
            "模型不可用（404 UnsupportedModel）：kimi-k3 需要 Agent Plan Medium 及以上"
            "套餐（Small 档不可用）；套餐过期也会报同一错误。"
        )
    if status == 400:
        return f"参数被拒（400 InvalidParameter）：{message or '详见响应'}"
    return f"HTTP {status} {err.get('code', '')}：{message}"


def extract_label(content):
    """回答里恰好命中一个分类词则返回它，否则 None。"""
    if not content:
        return None
    hits = [label for label in LABELS if label in content]
    return hits[0] if len(hits) == 1 else None


def usage_of(body):
    """返回 (completion_tokens, reasoning_tokens)，取不到则为 (None, 0)。"""
    usage = (body or {}).get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return usage.get("completion_tokens"), details.get("reasoning_tokens", 0)


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print("失败：环境变量 ARK_AGENT_PLAN_API_KEY 未设置。请在 Agent Plan 控制台"
              "「使用配置 → 配置专属API Key」获取专属 Key 并 export 后重试。")
        return 1

    failures = []  # 每个方案的失败原因，最终汇总打印
    for attempt in (ATTEMPT_1, ATTEMPT_2):
        print(f"[尝试] {attempt['name']} ...")
        status, body, err = call_api(api_key, attempt["payload"])

        if err is not None:  # 网络层失败（超时/连接/非 JSON 响应）
            failures.append(f"{attempt['name']}：{err}")
            continue

        if status != 200:
            reason = explain_http_error(status, body)
            failures.append(f"{attempt['name']}：{reason}")
            if status in (401, 403, 404):
                # 鉴权 / 套餐档位问题，换参数也救不回来，直接结束并说明原因
                print("\n拿不到分类结果，原因：")
                for line in failures:
                    print(f"  - {line}")
                return 1
            continue  # 400 等参数问题：换下一方案的参数再试

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = (message.get("content") or "").strip()
        finish_reason = choice.get("finish_reason", "")
        completion_tokens, reasoning_tokens = usage_of(body)

        label = extract_label(content)
        if label:
            print(f"\n分类结果：{label}")
            print(f"待分类句子：{TEXT}")
            print(f"命中方案：{attempt['name']}")
            print(f"实际输出用量：completion_tokens={completion_tokens}，"
                  f"其中思维链 reasoning_tokens={reasoning_tokens}")
            if completion_tokens is not None and completion_tokens <= 64:
                print("✓ 输出 ≤ 64 token 的成本目标达成（思考已关，64 上限只作用在回答上）。")
            else:
                print("✗ 「输出 ≤ 64 token」未能达成，原因：kimi-k3 是思考模型，其输出上限"
                      "（max_tokens / max_completion_tokens 均如此）把思维链计入额度——实测 64 "
                      "上限时思维链（本题量级就有 61+ token）会吃光预算，finish_reason="
                      "\"length\"、content 为空；而关闭思考（thinking.disabled）未被本模型"
                      "接受或未生效。要拿到分类结果，输出预算必须为思维链留出空间，本次实际"
                      "用量见上（计费按实际生成 token，不按上限值）。")
            return 0

        # HTTP 200 但没拿到可用回答：记录详细证据，落到下一方案
        if finish_reason == "length" or not content:
            failures.append(
                f"{attempt['name']}：HTTP 200 但回答为空（finish_reason={finish_reason!r}，"
                f"completion_tokens={completion_tokens}，reasoning_tokens={reasoning_tokens}）"
                "——思维链耗尽了输出上限，没有剩余预算生成回答。"
            )
        else:
            failures.append(
                f"{attempt['name']}：HTTP 200 但回答不是三个分类词之一"
                f"（finish_reason={finish_reason!r}，content={content!r}）。"
            )
        print(f"  未拿到结果（finish_reason={finish_reason!r}，"
              f"completion_tokens={completion_tokens}，"
              f"reasoning_tokens={reasoning_tokens}），换下一方案。")

    print("\n拿不到分类结果，已尝试的方案与失败原因（按顺序）：")
    for line in failures:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
