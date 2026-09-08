#!/usr/bin/env python3
"""用智谱 GLM 给商品评论做一句话摘要。

成本控制：每条评论单独调用一次 chat/completions，max_tokens=32 硬性限制
单条回复的输出预算（max_tokens 只限制输出，不含输入 prompt）。

可靠性约定：拿不到摘要时打印具体原因（HTTP/业务错误、思考内容耗尽预算导致
content 为空、输出被截断、内容被安全审核拦截等），绝不用空字符串冒充成功；
只要有任何一条失败，进程退出码为 1。

用法：
    export ZHIPUAI_API_KEY=<你的 API Key>
    python3 main.py
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型选型（这直接决定 32 token 预算是否可行）：
# - glm-5.3 / glm-5.3-flash / glm-4.7 强制开启思考，且思考内容同样消耗
#   max_tokens：32 个 token 会被思考过程吃光，content 只能拿到空字符串；
# - glm-4.5-flash 免费（评论量大时成本最优），属于支持 thinking.type=disabled
#   的 GLM-4.5 系列，关掉思考后 32 token 足够输出一句话摘要。
MODEL = "glm-4.5-flash"

MAX_TOKENS = 32        # 每条回复的 token 预算上限
TEMPERATURE = 0.2
REQUEST_TIMEOUT = 30   # 秒
MAX_HTTP_ATTEMPTS = 3  # 网络/限流/服务端错误的重试次数

# 先要求 20 字以内；若 32 token 装不下（content 为空或被截断），再用 12 字重试一次
CHAR_LIMITS = (20, 12)

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

SYSTEM_PROMPT = "你是电商评论摘要助手。只输出摘要本身，不要引号、编号或任何解释。"


class SummaryError(Exception):
    """摘要获取失败；message 是给人看的具体原因。"""

    def __init__(self, reason, retry_shorter=False):
        super().__init__(reason)
        # retry_shorter=True 表示"缩短摘要要求后重试"有可能解决（如输出被截断）
        self.retry_shorter = retry_shorter


def build_payload(review, char_limit):
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "用一句话中文概括这条商品评论，不超过%d个字，直接给出结论：\n%s"
                    % (char_limit, review)
                ),
            },
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        # 关键参数：GLM 的思考内容同样计入 max_tokens，且部分模型默认开启思考。
        # 不显式关掉的话，32 个 token 会被思考过程耗尽，最终 message.content
        # 是空字符串、思考内容全在 message.reasoning_content 里——这是小预算下
        # 最常见的"拿到空回复"原因。
        "thinking": {"type": "disabled"},
    }


def http_error_detail(resp):
    try:
        err = (resp.json() or {}).get("error") or {}
        return "code=%s message=%s" % (err.get("code"), err.get("message"))
    except ValueError:
        return resp.text[:200]


def call_api(api_key, payload):
    """POST 一次接口并返回解析后的 JSON。网络异常、429、5xx 退避重试；其余直接抛错。"""
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": "Bearer " + api_key},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            if attempt == MAX_HTTP_ATTEMPTS:
                raise SummaryError(
                    "网络请求失败（已重试 %d 次）：%r" % (MAX_HTTP_ATTEMPTS, exc)
                )
            time.sleep(attempt)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                raise SummaryError("HTTP 200 但返回体不是 JSON：%r" % resp.text[:200])

        detail = http_error_detail(resp)
        if (resp.status_code == 429 or resp.status_code >= 500) and attempt < MAX_HTTP_ATTEMPTS:
            time.sleep(attempt)  # 限流/服务端抖动，退避后重试
            continue
        raise SummaryError("HTTP %d：%s" % (resp.status_code, detail))

    raise SummaryError("请求未能完成（已尝试 %d 次）" % MAX_HTTP_ATTEMPTS)


def extract_summary(data):
    """校验响应并取出摘要文本；拿不到就抛带具体原因的 SummaryError。"""
    err = data.get("error")
    if err:
        raise SummaryError(
            "接口业务错误：code=%s message=%s" % (err.get("code"), err.get("message"))
        )

    choices = data.get("choices") or []
    if not choices:
        raise SummaryError(
            "响应中没有 choices：%s" % json.dumps(data, ensure_ascii=False)[:300]
        )

    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    completion_tokens = (data.get("usage") or {}).get("completion_tokens")

    if finish_reason == "sensitive":
        raise SummaryError("内容被安全审核拦截（finish_reason=sensitive），拿不到摘要")
    if finish_reason == "network_error":
        raise SummaryError("模型推理异常（finish_reason=network_error），请稍后重试")

    if not content:
        reasons = [
            "返回的 content 为空（finish_reason=%s，completion_tokens=%s）"
            % (finish_reason, completion_tokens)
        ]
        if message.get("reasoning_content"):
            # 小预算下的经典坑：思考内容占满了 max_tokens，正文一个 token 都没分到
            reasons.append(
                "思考内容出现在 reasoning_content 里并耗尽了 max_tokens=%d 的预算，"
                "说明思考并没有真正关掉（请改用支持 thinking.type=disabled 的模型，"
                "或调大预算）" % MAX_TOKENS
            )
        raise SummaryError("；".join(reasons), retry_shorter=not message.get("reasoning_content"))

    if finish_reason == "length":
        raise SummaryError(
            "32 token 预算内装不下完整摘要，输出被截断（completion_tokens=%s），"
            "截断前的半截内容：%s" % (completion_tokens, content),
            retry_shorter=True,
        )

    return content


def summarize(review, api_key):
    """对单条评论调用 GLM，成功返回 (摘要文本, usage 字典)，失败抛 SummaryError。"""
    last_error = None
    for char_limit in CHAR_LIMITS:
        data = call_api(api_key, build_payload(review, char_limit))
        try:
            content = extract_summary(data)
        except SummaryError as exc:
            last_error = exc
            if not exc.retry_shorter:
                raise
            continue  # 预算装不下，换更短的摘要要求再试一次
        return content, data.get("usage") or {}

    raise SummaryError("已尝试缩短摘要仍未成功，最后一次原因：%s" % last_error)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        print("请先执行：export ZHIPUAI_API_KEY=<你的 API Key>", file=sys.stderr)
        return 1

    ok_count = 0
    for index, review in enumerate(REVIEWS, 1):
        print("[%d] 原文：%s" % (index, review))
        try:
            summary, usage = summarize(review, api_key)
        except SummaryError as exc:
            print("    摘要：获取失败——%s" % exc)
            print()
            continue
        print("    摘要：%s" % summary)
        print(
            "    （本次输出 %s/%d token）"
            % (usage.get("completion_tokens", "?"), MAX_TOKENS)
        )
        print()
        ok_count += 1

    if ok_count == len(REVIEWS):
        print("完成：%d/%d 条摘要全部成功，单条输出均未超过 %d token。" % (ok_count, len(REVIEWS), MAX_TOKENS))
        return 0
    print("未完成：仅 %d/%d 条摘要成功，失败原因见上，退出码置为 1。" % (ok_count, len(REVIEWS)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
