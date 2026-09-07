#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用火山方舟 Agent Plan 的 kimi-k3 对一句话做情感分类（只允许输出「正面」「负面」「中性」）。

运行方式：
    export ARK_AGENT_PLAN_API_KEY="ark-xxxxxxxx"    # 火山方舟控制台创建的 Agent Plan API Key
    python3 main.py

设计要点（成本敏感场景）：
1. 首选请求 max_tokens=64，满足“输出上限压到 64 token 以内”的要求。
2. 关键坑：kimi-k3 是深度思考模型。Ark 的 Chat API 中，思维链（reasoning）token 与
   最终回答共用同一个 max_tokens 上限，且 thinking 参数不传时深度思考默认开启。
   若不关闭思考，64 个 token 会被思维链耗尽——返回的 content 是空字符串、
   finish_reason="length"，即“设了小 max_tokens 却拿到空结果”的根因。
   因此首选请求同时显式传 thinking={"type": "disabled"}，把 64 个 token 全部留给最终回答。
3. 拿到响应后严格校验：content 必须解析出「正面/负面/中性」三者之一才算成功；
   解析不出就结合 finish_reason / reasoning_content / usage 给出明确的中文原因，
   并做一次“放宽输出上限”的兜底重试（会打印原因与实际 token 消耗）。
   两次都拿不到结果则打印完整诊断并以非零码退出——绝不把空结果当成功输出。
"""

import json
import os
import sys

try:
    import requests
except ImportError:
    print("错误：缺少第三方库 requests，请先安装：pip3 install requests", file=sys.stderr)
    sys.exit(1)

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
MODEL = "kimi-k3"
TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")

MAX_TOKENS = 64              # 用户要求的输出上限
FALLBACK_MAX_TOKENS = 2048   # 首选方案拿不到结果时，一次性兜底调用的输出上限
TIMEOUT = (10, 180)          # (连接超时, 读取超时)，单位秒

# Agent Plan 的 OpenAI 兼容 v3 专属地址；万一网关返回 404，再退回标准 /api/v3 地址
BASE_URLS = (
    "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions",
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
)

SYSTEM_PROMPT = (
    "你是情感分类器。判断用户句子的情感倾向，"
    "只输出「正面」「负面」「中性」三个词中的一个词，"
    "不要输出任何解释、标点或其他文字。"
)


def warn(msg):
    print(msg, file=sys.stderr)


def build_payload(max_tokens, disable_thinking=True):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TEXT},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    if disable_thinking:
        # 不关思考的话，思考 token 与回答共用 max_tokens，小预算下 content 会是空的
        payload["thinking"] = {"type": "disabled"}
    return payload


def describe_http_error(resp):
    detail = resp.text[:500] if resp.text else "(无响应体)"
    try:
        body = resp.json()
        err = body.get("error")
        if isinstance(err, dict):
            detail = err.get("message") or json.dumps(err, ensure_ascii=False)
        elif err is not None:
            detail = str(err)
    except ValueError:
        pass
    hints = {
        401: "（API Key 无效或未传入）",
        403: "（Key 未开通 Agent Plan，或无权调用 kimi-k3）",
        404: "（接口地址或模型名不可用）",
        429: "（触发限流或套餐额度不足）",
    }
    return "HTTP %d%s：%s" % (resp.status_code, hints.get(resp.status_code, ""), detail)


def call_model(api_key, payload):
    """发起一次请求。成功返回 (响应JSON, None)；失败返回 (None, 中文错误说明)。"""
    headers = {"Authorization": "Bearer " + api_key}
    for i, url in enumerate(BASE_URLS):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            return None, "请求超时（连接或读取超时），请检查本机网络后重试。"
        except requests.exceptions.RequestException as exc:
            return None, "网络请求失败：%s" % exc
        if resp.status_code == 404 and i < len(BASE_URLS) - 1:
            warn("[info] %s 返回 404，改用备用地址 %s" % (url, BASE_URLS[i + 1]))
            continue
        if resp.status_code != 200:
            return None, describe_http_error(resp)
        try:
            data = resp.json()
        except ValueError:
            return None, "HTTP 200 但响应体不是合法 JSON：%r" % resp.text[:500]
        err = data.get("error")
        if err is not None:
            return None, "服务端返回错误：%s" % (
                err.get("message") if isinstance(err, dict) else err)
        if not data.get("choices"):
            return None, "响应中没有 choices，原始返回：%s" % json.dumps(data, ensure_ascii=False)[:500]
        return data, None
    return None, "所有接口地址均不可用。"


def inspect_choice(data):
    """从响应 JSON 里取出生成内容与诊断信息。"""
    choice = data["choices"][0]
    message = choice.get("message") or {}
    raw_content = message.get("content")
    content = raw_content.strip() if isinstance(raw_content, str) else ""
    raw_reasoning = message.get("reasoning_content")
    reasoning = raw_reasoning.strip() if isinstance(raw_reasoning, str) else ""
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens")
    usage_desc = "completion_tokens=%s, reasoning_tokens=%s, finish_reason=%s" % (
        usage.get("completion_tokens"), reasoning_tokens, finish_reason)
    # 是否“预算被思考吃掉”：响应里有思维链痕迹，或因达到长度上限被截断
    thinking_ate = bool(reasoning) or (
        isinstance(reasoning_tokens, int) and reasoning_tokens > 0) or finish_reason == "length"
    return content, reasoning, finish_reason, usage_desc, thinking_ate


def extract_label(content):
    """从模型输出解析标签。返回 (标签或None, 解析方式说明)。"""
    t = content.strip().strip("「」『』“”‘’\"' \t\r\n").rstrip("。．.!！?？~～ ")
    if t in LABELS:
        return t, "精确匹配"
    hits = [label for label in LABELS if label in content]
    if len(hits) == 1:
        return hits[0], "从多余文字中提取（模型未严格遵守“只输出一个词”）"
    return None, None


def run_attempt(api_key, payload, tag):
    """跑一次请求并评估。返回 (标签或None, 诊断行列表, HTTP层错误或None)。"""
    data, err = call_model(api_key, payload)
    if err is not None:
        return None, ["%s 调用失败：%s" % (tag, err)], err
    content, reasoning, finish_reason, usage_desc, thinking_ate = inspect_choice(data)
    label, how = extract_label(content)
    lines = ["%s 返回：content=%r（%s）" % (tag, content, usage_desc)]
    if label is not None:
        lines.append("%s 成功解析出标签：%s（%s）" % (tag, label, how))
        return label, lines, None
    if not content:
        if thinking_ate:
            lines.append(
                "  → content 为空。原因：kimi-k3 是深度思考模型，思维链 token 与最终回答"
                "共用同一个 max_tokens 上限；本次上限内的 token 已被思考耗尽"
                "（finish_reason=%s），正式回答还没开始生成就被截断。" % finish_reason)
        else:
            lines.append(
                "  → content 为空，且响应里没有思考痕迹（finish_reason=%s），"
                "模型没有产出任何答案。" % finish_reason)
    else:
        lines.append("  → 模型输出不是「正面/负面/中性」之一，无法作为分类结果。")
    return None, lines, None


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        warn("错误：没有找到 API Key。请先在火山方舟控制台创建 Agent Plan 的 API Key，再设置环境变量：")
        warn('  export %s="ark-xxxxxxxx"' % API_KEY_ENV)
        return 1

    # ---- 尝试 1（首选，满足 ≤64 token）：关闭深度思考，64 个 token 全部留给最终回答 ----
    warn("[尝试1] model=%s, thinking=disabled, max_tokens=%d" % (MODEL, MAX_TOKENS))
    label, lines, err = run_attempt(api_key, build_payload(MAX_TOKENS), "[尝试1]")
    for line in lines:
        warn(line)
    if label is not None:
        print(label)  # stdout 只输出分类结果本身
        return 0

    # ---- 拿不到结果：先解释原因，再做一次兜底重试 ----
    if err is not None:
        if "thinking" in err.lower():
            warn("[尝试2] thinking 参数被网关/模型拒绝。改为不传 thinking（默认开启思考），"
                 "并把输出上限放宽到 %d token，确保能拿到结果……" % FALLBACK_MAX_TOKENS)
            payload2 = build_payload(FALLBACK_MAX_TOKENS, disable_thinking=False)
        else:
            warn("错误：首选调用在 HTTP 层就失败了（不是“结果为空”），重试无意义，退出。")
            return 1
    else:
        warn("[尝试2] 64 token 上限下拿不到结果（原因见上方诊断）。为满足“必须拿到分类结果”"
             "的前提，保持思考关闭、把输出上限一次性放宽到 %d token 重试……" % FALLBACK_MAX_TOKENS)
        payload2 = build_payload(FALLBACK_MAX_TOKENS, disable_thinking=True)

    label2, lines2, err2 = run_attempt(api_key, payload2, "[尝试2]")
    for line in lines2:
        warn(line)
    if label2 is not None:
        print(label2)
        warn("[提示] 本次为拿到结果放宽了输出上限，64 token 的成本目标未达成，原因见上方诊断。")
        return 0

    if err2 is not None:
        warn("错误：兜底调用也在 HTTP 层失败，未能拿到分类结果。")
    else:
        warn("错误：两次调用都无法解析出「正面/负面/中性」之一的分类结果，完整原因见上方诊断。")
    warn("本脚本不会把空结果当成功输出。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
