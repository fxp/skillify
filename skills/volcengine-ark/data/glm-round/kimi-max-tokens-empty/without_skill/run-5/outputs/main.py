#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用火山方舟 Agent Plan 的 kimi-k3 做情感分类。

对「这家店的服务态度太差了，再也不来了」判断情感，只输出「正面」「负面」「中性」之一。

为什么不能简单地 max_tokens=64 一把梭：
  kimi-k3 是"思考永远开启"的推理模型（官方文档：kimi-k3 always reasons and does
  not support the `thinking` parameter），思考 token 与正文共用 max_tokens 预算
  （reasoning_content + content 之和不得超过 max_tokens，官方建议思考模型
  max_tokens >= 16000）。因此把输出上限压到 64 token 时，思考极可能先把预算
  吃光，最终 content 为空、finish_reason="length"。

本脚本的策略：
  1) 先在 64 token 预算内尝试，并把推理强度 reasoning_effort 压到最低档，力求预算内拿到结果；
  2) 若预算内拿不到，如实打印失败原因（不会用空结果冒充成功）；
  3) 用户的前提是"必须真的拿到分类结果"，所以随后逐级放宽 max_tokens 兜底，
     并明确标注最终是否超出 64 预算、实际消耗多少 token；
  4) 全部尝试失败时，汇总每一步的具体原因后以非零码退出。

用法：
    export ARK_AGENT_PLAN_API_KEY=xxx   # 必填
    export ARK_MODEL=kimi-k3            # 可选，默认 kimi-k3
    python3 main.py
"""

import json
import os
import sys

import requests

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
MODEL_ENV = "ARK_MODEL"
DEFAULT_MODEL = "kimi-k3"
API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

TEXT_TO_CLASSIFY = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")
TOKEN_BUDGET = 64  # 用户期望的单次调用输出上限

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的文本判断情感，"
    "只输出「正面」「负面」「中性」三个词之一，"
    "不要输出任何解释、标点或其他内容。"
)

# 尝试序列：(reasoning_effort, max_tokens)。
# 前两步严格在 64 预算内；后两步是"必须拿到结果"前提下的兜底，逐级放宽。
# 16384 依据官方对思考模型 max_tokens >= 16000 的建议。
ATTEMPTS = [
    ("none", 64),
    ("low", 64),
    ("low", 1024),
    ("low", 16384),
]

TIMEOUT = (10, 300)  # 连接 10s，读取 300s（思考模型响应偏慢）


def extract_label(text):
    """从模型输出中提取情感标签，提取不到返回 None。"""
    cleaned = text.strip().rstrip("。.!！?？\n\t ")
    if cleaned in LABELS:
        return cleaned
    found = [(text.find(label), label) for label in LABELS if label in text]
    found = [item for item in found if item[0] >= 0]
    if found:
        found.sort()
        return found[0][1]
    return None


def describe_api_error(resp):
    """把非 200 响应整理成人能读的错误描述。"""
    try:
        body = resp.json()
        err = body.get("error") or body
        code = err.get("code", body.get("code"))
        message = err.get("message", body.get("message"))
        if message:
            return f"HTTP {resp.status_code} code={code} message={message}"
        return f"HTTP {resp.status_code} 响应体={json.dumps(body, ensure_ascii=False)[:300]}"
    except ValueError:
        return f"HTTP {resp.status_code} 响应体={resp.text[:300]!r}"


def usage_brief(usage):
    """摘要 usage 信息，重点看输出 token 与思考 token。"""
    if not usage:
        return "无 usage 字段"
    completion = usage.get("completion_tokens")
    details = usage.get("completion_tokens_details") or {}
    reasoning = details.get("reasoning_tokens")
    prompt = usage.get("prompt_tokens")
    parts = [f"prompt_tokens={prompt}", f"completion_tokens={completion}"]
    if reasoning is not None:
        parts.append(f"reasoning_tokens={reasoning}")
    return ", ".join(parts)


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"[配置错误] 环境变量 {API_KEY_ENV} 未设置，无法调用 API。", file=sys.stderr)
        print(f"请先执行：export {API_KEY_ENV}=你的AgentPlanAPIKey", file=sys.stderr)
        return 2

    model = os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"待分类文本：{TEXT_TO_CLASSIFY}"},
    ]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    failures = []          # 每次尝试的失败原因
    effort_rejected = False  # 平台/模型拒绝 reasoning_effort 参数后，后续不再携带

    for index, (effort, max_tokens) in enumerate(ATTEMPTS, start=1):
        in_budget = max_tokens <= TOKEN_BUDGET
        effort_desc = f"reasoning_effort={effort}" if effort else "不携带 reasoning_effort"
        print(f"[尝试 {index}/{len(ATTEMPTS)}] model={model}, max_tokens={max_tokens}, {effort_desc}")

        if not in_budget:
            print(f"  ⚠ 注意：本次已超出 {TOKEN_BUDGET} token 预算（兜底尝试，见脚本头部说明）。")

        payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if effort and not effort_rejected:
            payload["reasoning_effort"] = effort

        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            reason = f"网络/请求异常：{exc!r}"
            print(f"  失败：{reason}")
            failures.append(reason)
            continue

        if resp.status_code != 200:
            reason = describe_api_error(resp)
            print(f"  失败：{reason}")
            failures.append(reason)
            # 若是 reasoning_effort 参数不被接受（400 + 报文点名该字段），后续尝试移除
            if resp.status_code == 400 and "reasoning_effort" in reason:
                effort_rejected = True
                print("  ↳ 检测到 reasoning_effort 参数被拒绝，后续尝试将不携带该参数。")
            # 鉴权/权限/限流类错误重试也无意义，直接进入失败汇总
            if resp.status_code in (401, 403):
                break
            continue

        try:
            data = resp.json()
        except ValueError:
            reason = f"HTTP 200 但响应不是合法 JSON：{resp.text[:300]!r}"
            print(f"  失败：{reason}")
            failures.append(reason)
            continue

        choices = data.get("choices") or []
        if not choices:
            reason = f"响应缺少 choices：{json.dumps(data, ensure_ascii=False)[:300]}"
            print(f"  失败：{reason}")
            failures.append(reason)
            continue

        choice = choices[0]
        message = choice.get("message") or {}
        content = (message.get("content") or "").strip()
        reasoning_content = message.get("reasoning_content") or ""
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage") or {}

        if not content:
            # 典型情形：kimi-k3 思考无法关闭，思考 token 计入 max_tokens，
            # 64 的预算被思考耗尽，finish_reason=length，content 为空。
            reason = (
                f"content 为空（finish_reason={finish_reason}；{usage_brief(usage)}；"
                f"思考内容已生成 {len(reasoning_content)} 字）"
            )
            print(f"  失败：{reason}")
            failures.append(reason)
            continue

        label = extract_label(content)
        if label is None:
            reason = f"模型输出了内容但解析不出三个标签之一，原始输出：{content[:120]!r}"
            print(f"  失败：{reason}")
            failures.append(reason)
            continue

        # 真正拿到了分类结果
        print(f"  成功：模型原始输出={content!r}")
        completion_tokens = usage.get("completion_tokens")
        budget_note = (
            f"实际输出 {completion_tokens} token，在 {TOKEN_BUDGET} 预算内"
            if in_budget
            else f"超出 {TOKEN_BUDGET} 预算（原因：kimi-k3 思考无法关闭，思考 token 与正文共享 max_tokens，"
                 f"64 以内拿不到正文），实际输出 {completion_tokens} token"
        )
        print(f"  token 用量：{usage_brief(usage)}")
        print(f"  预算情况：{budget_note}")
        print(f"\n情感分类结果：{label}")
        return 0

    # 走到这里说明一次都没拿到
    print("\n[失败] 未能拿到分类结果，各次尝试的原因如下：", file=sys.stderr)
    for i, reason in enumerate(failures, start=1):
        print(f"  {i}. {reason}", file=sys.stderr)
    if any("content 为空" in reason for reason in failures):
        print(
            "结论：kimi-k3 是思考常开的推理模型，不支持 thinking 参数关闭思考，"
            "且思考 token 计入 max_tokens（官方建议思考模型 max_tokens>=16000），"
            "因此 64 token 的输出上限内拿不到正文。",
            file=sys.stderr,
        )
    print(
        "建议排查：1) API Key 是否有效、Agent Plan 是否包含 kimi-k3（Medium 档及以上）；"
        "2) 模型 ID 是否正确（可用 ARK_MODEL 环境变量覆盖，"
        "确切 ID 请在火山方舟控制台「模型广场」确认）；"
        "3) 是否触发限流（Agent Plan 额度按 5 小时/周/月周期刷新）。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
