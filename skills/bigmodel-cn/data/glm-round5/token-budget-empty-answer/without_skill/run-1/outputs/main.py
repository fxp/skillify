#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 给商品评论生成一句话摘要。

每条评论单独调用一次 chat/completions，max_tokens=32 压住单条回复成本。
注意：GLM 混合推理模型默认开启深度思考，且思考 token 计入 max_tokens——
预算这么小时必须显式传 thinking={"type": "disabled"}，否则思考会先耗尽
预算，返回的 content 是空字符串。脚本对每条拿不到摘要的情况给出明确
原因，绝不打印空字符串冒充完成。

用法:
    export ZHIPUAI_API_KEY=你的key
    python3 main.py
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# glm-4.5-flash 免费且支持关闭思考；要换模型可用环境变量 ZHIPUAI_MODEL 覆盖
# （GLM-5.3 系列无法关闭思考，不适用于 32 token 这种小预算场景）
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.5-flash")
MAX_TOKENS = 32   # 每条回复的 token 预算上限
MAX_RETRIES = 3   # 仅对网络错误 / 429 / 5xx 重试
TIMEOUT = 30      # 秒

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

SYSTEM_PROMPT = "你是商品评论摘要助手，只输出一句中文摘要，不加任何解释或前缀。"
USER_TEMPLATE = "用一句话（20字以内）概括这条商品评论的核心评价：\n%s"


def extract_error(resp):
    """从错误响应体里尽量带出官方的 error.code / error.message。"""
    try:
        err = resp.json().get("error") or {}
        return "code=%s, message=%s" % (err.get("code"), err.get("message"))
    except ValueError:
        pass
    body = (resp.text or "").strip()
    return body[:200] if body else "(响应体为空)"


def parse_response(resp):
    """解析一次已送达的响应，返回 (错误信息, 摘要, completion_tokens)。

    成功时错误信息为 None；失败时摘要为 None，错误信息说明具体原因。
    """
    if resp.status_code != 200:
        return "HTTP %d: %s" % (resp.status_code, extract_error(resp)), None, None

    try:
        data = resp.json()
    except ValueError:
        return "响应不是合法 JSON: %r" % resp.text[:200], None, None

    if data.get("error"):
        err = data["error"]
        return "API 返回错误 code=%s: %s" % (err.get("code"), err.get("message")), None, None

    choices = data.get("choices") or []
    if not choices:
        return "响应里没有 choices: %s" % json.dumps(data, ensure_ascii=False)[:300], None, None

    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    completion_tokens = (data.get("usage") or {}).get("completion_tokens")

    if not content:
        # 拿不到正文：按 finish_reason 给出明确原因，而不是返回空摘要装作成功
        if finish_reason == "length":
            return ("模型输出在 %d 个 token 处被截断且 content 为空——"
                    "通常是深度思考耗尽了预算，请确认模型 %s 支持 thinking disabled"
                    % (MAX_TOKENS, MODEL)), None, None
        if finish_reason == "sensitive":
            return "内容被安全审核拦截(finish_reason=sensitive)", None, None
        if (message.get("reasoning_content") or "").strip():
            return ("content 为空但 reasoning_content 非空(finish_reason=%s)，"
                    "思考并未真正关闭" % finish_reason), None, None
        return "content 为空(finish_reason=%s)" % finish_reason, None, None

    if finish_reason == "length":
        return ("摘要被 %d token 预算截断(finish_reason=length)，内容不完整: %r"
                % (MAX_TOKENS, content)), None, None

    if completion_tokens is not None and completion_tokens > MAX_TOKENS:
        return ("摘要超出预算: completion_tokens=%d > %d"
                % (completion_tokens, MAX_TOKENS)), None, None

    return None, content, completion_tokens


def summarize_review(api_key, review):
    """对单条评论调用 GLM，返回 (错误信息, 摘要, completion_tokens)。"""
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE % review},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        # 关键：思考 token 计入 max_tokens，32 的预算必须显式关闭深度思考，
        # 否则思考先把预算耗尽，content 返回空字符串
        "thinking": {"type": "disabled"},
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                time.sleep(attempt)  # 网络抖动，退避后重试
                continue
            return "网络请求失败(已重试%d次): %s" % (MAX_RETRIES, exc), None, None

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < MAX_RETRIES:
                time.sleep(attempt)
                continue
            return ("HTTP %d(已重试%d次): %s"
                    % (resp.status_code, MAX_RETRIES, extract_error(resp))), None, None

        return parse_response(resp)  # 200 和 4xx 都不重试，直接解析

    return "重试次数耗尽", None, None


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API。", file=sys.stderr)
        print("请先执行: export ZHIPUAI_API_KEY=你的APIKey", file=sys.stderr)
        return 1

    print("模型: %s | 每条回复 token 预算: %d | 评论数: %d\n" % (MODEL, MAX_TOKENS, len(REVIEWS)))
    failures = 0
    for idx, review in enumerate(REVIEWS, 1):
        error, summary, completion_tokens = summarize_review(api_key, review)
        print("【评论%d】%s" % (idx, review))
        if error:
            failures += 1
            print("  摘要失败: %s" % error)
        else:
            budget = ("%d/%d tokens" % (completion_tokens, MAX_TOKENS)
                      if completion_tokens is not None else "预算未验证(响应缺 usage)")
            print("  摘要: %s（%s）" % (summary, budget))
        print()

    if failures:
        print("%d/%d 条评论未拿到摘要，原因见上。" % (failures, len(REVIEWS)), file=sys.stderr)
        return 1
    print("全部 %d 条摘要完成，均在 %d token 预算内。" % (len(REVIEWS), MAX_TOKENS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
