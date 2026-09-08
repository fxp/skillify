#!/usr/bin/env python3
"""用智谱 GLM（bigmodel.cn）给商品评论各生成一句话摘要。

硬约束：每条回复的输出 token 预算 ≤ 32（max_tokens=32 硬限制，
并回显实际 completion_tokens 供核对；1 token ≈ 1.5 个中文字符，
32 token 约 48 字，"不超过 20 字"的摘要有安全余量）。

两个关键设计，缺一个都会掉进"拿到空摘要还以为成功了"的坑：
1. 模型选 glm-4.5-flash：免费（评论量大时成本为零），且属于 GLM-4.5 系列、
   支持显式关闭深度思考。不要换成 glm-5.3 / glm-5.3-flash——它们在标准端点
   强制思考（传 thinking.type=disabled 会报 1210），32 个 token 会被思维链
   耗尽，message.content 返回空字符串、finish_reason=length。
2. 每次调用后校验正文非空；拿不到就根据 finish_reason / usage 给出明确原因
   并按失败处理，绝不打印空字符串冒充成功。

大批量场景提示：同步接口的限流按并发数计算，真正上生产建议改走
Batch API 或异步对话接口（POST /paas/v4/async/chat/completions）。

用法：
    export ZHIPUAI_API_KEY=<你的Key>   # https://bigmodel.cn/usercenter/proj-mgmt/apikeys
    python3 main.py
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.5-flash"
MAX_TOKENS = 32
MAX_RETRIES = 3  # 含首次请求
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

# 固定不变的 system 提示词还有个好处：多次请求间前缀完全一致，更容易命中
# 平台的隐式上下文缓存（usage.prompt_tokens_details.cached_tokens），压低输入成本。
SYSTEM_PROMPT = (
    "你是商品评论摘要助手。对用户给出的一条商品评论输出一句话中文摘要，"
    "要求：不超过20个字；优点和缺点都要保留（如有）；"
    "直接输出摘要正文，不要引号、序号、前后缀或任何解释。"
)


class SummaryError(Exception):
    """拿不到摘要时，message 里写清楚原因。"""


def _http_error_summary(resp):
    """把平台错误体 {"error":{"code":..,"message":..}} 拼成可读字符串。"""
    try:
        err = resp.json().get("error") or {}
        code = err.get("code", "?")
        message = err.get("message") or resp.text[:200]
    except ValueError:
        code, message = "?", resp.text[:200]
    hint = ""
    if code == "1113":
        hint = "（若这是 GLM Coding Plan 套餐 Key：它不能打标准端点，请换标准 API Key）"
    return f"HTTP {resp.status_code}，业务错误码 {code}: {message}{hint}"


def _request(api_key, payload):
    """发起请求，带指数退避重试（仅对 429/5xx 和网络异常重试）。"""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:
            last_err = f"网络异常: {exc!r}"
        else:
            if resp.status_code == 200:
                return resp
            last_err = _http_error_summary(resp)
            if resp.status_code not in RETRYABLE_STATUS:
                # 4xx 是鉴权/参数问题，重试没有意义，直接失败并说明原因
                raise SummaryError(last_err)
        if attempt < MAX_RETRIES:
            time.sleep(2 ** (attempt - 1))  # 1s, 2s
    raise SummaryError(f"重试 {MAX_RETRIES} 次后仍失败，最后一次原因：{last_err}")


# 正文为空时按 finish_reason 给出人话解释
_EMPTY_REASON = {
    "length": "输出在写出任何正文前就达到 max_tokens=32 上限"
              "（token 预算被思考内容耗尽的典型症状）",
    "sensitive": "生成内容触发平台内容安全策略，被拦截",
    "network_error": "模型推理异常（finish_reason=network_error）",
    "model_context_window_exceeded": "超出模型上下文窗口",
    "tool_calls": "模型返回的是工具调用而非正文（content 为 null）",
}


def summarize_review(api_key, review):
    """对单条评论调一次 API，返回 (摘要文本, finish_reason, usage)。

    返回的摘要保证是非空字符串；拿不到非空正文时抛 SummaryError 并说明原因。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"商品评论：{review}"},
        ],
        "thinking": {"type": "disabled"},  # 关键：不关思考，32 token 会被思维链耗尽
        "max_tokens": MAX_TOKENS,          # 每条回复 token 预算的硬上限
        "temperature": 0.3,
        "stream": False,
    }
    resp = _request(api_key, payload)
    try:
        data = resp.json()
    except ValueError as exc:
        raise SummaryError(
            f"响应体不是合法 JSON: {exc}；前 200 字符: {resp.text[:200]!r}"
        )

    choices = data.get("choices") or []
    if not choices:
        raise SummaryError(f"响应里没有 choices 字段: {data!r}")
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    content = content.strip() if isinstance(content, str) else ""
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")

    if not content:
        reason = _EMPTY_REASON.get(
            finish_reason, f"未预期的 finish_reason={finish_reason!r}"
        )
        if message.get("reasoning_content"):
            reason += "；且 reasoning_content 非空——思考内容吃掉了 token 预算"
        if completion_tokens is not None:
            reason += f"；completion_tokens={completion_tokens}"
        raise SummaryError(f"未拿到摘要正文：{reason}")

    return content, finish_reason, usage


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：环境变量 ZHIPUAI_API_KEY 未设置。请先 "
            "export ZHIPUAI_API_KEY=<你的Key>"
            "（获取地址 https://bigmodel.cn/usercenter/proj-mgmt/apikeys）",
            file=sys.stderr,
        )
        return 1

    ok = 0
    for i, review in enumerate(REVIEWS, 1):
        print(f"[{i}/{len(REVIEWS)}] 评论：{review}")
        try:
            summary, finish_reason, usage = summarize_review(api_key, review)
        except SummaryError as exc:
            print(f"       ✗ 未取得摘要：{exc}\n")
            continue

        completion = usage.get("completion_tokens", "?")
        if finish_reason == "stop":
            note = ""
        elif finish_reason == "length":
            note = "（已达 max_tokens 上限，摘要可能被截断，但拿到了非空文本）"
        else:
            note = f"（finish_reason={finish_reason}）"
        if isinstance(completion, int) and completion > MAX_TOKENS:
            note += f"（异常：completion_tokens={completion} 超出预算 {MAX_TOKENS}）"
        print(f"       ✓ 摘要：{summary}")
        print(f"         token 用量：completion_tokens={completion}/{MAX_TOKENS}{note}\n")
        ok += 1

    if ok == len(REVIEWS):
        print(f"全部 {ok} 条评论均取得非空摘要，单条输出 token 控制在 {MAX_TOKENS} 以内。")
        return 0
    print(f"仅 {ok}/{len(REVIEWS)} 条取得摘要，失败原因见上方各条。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
