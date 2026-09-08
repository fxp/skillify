#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 给商品评论做一句话摘要，每条回复 token 预算硬上限 32。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

两个核心约束的实现：
- 压成本：选免费档模型 glm-4.7-flash，max_tokens=32 钉死输出预算，prompt 也尽量短。
- 拿不到摘要绝不装成功：任何一条失败都会打印具体原因
  （HTTP 状态码/错误码、finish_reason、reasoning_content、usage），并以退出码 1 结束。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.7-flash"  # 免费档。注意 GLM-5.3 系列不允许关闭思考，故不用
MAX_TOKENS = 32  # 每条回复的 token 预算（硬上限，绝不为了出结果调大）
TIMEOUT = 30  # 单次请求超时（秒）
MAX_ATTEMPTS = 3  # 只对网络错误/限流/5xx 重试

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

# 32 个 token 约 25 个汉字，要求 20 字以内给截断留余量
PROMPT_TMPL = (
    "用一句话概括这条商品评论，保留好评点和差评点，20字以内，"
    "直接输出摘要正文，不要引号、序号或解释。评论：{review}"
)


def _describe_http_error(resp: requests.Response) -> str:
    """把非 200 响应整理成人能看懂的原因。"""
    try:
        err = (resp.json() or {}).get("error") or {}
        detail = "code={code}, message={message}".format(
            code=err.get("code"), message=err.get("message")
        )
    except ValueError:
        detail = "响应非 JSON：{!r}".format(resp.text[:200])
    hints = {
        401: "（API Key 无效，检查 ZHIPUAI_API_KEY）",
        403: "（Key 无该模型权限或账户欠费）",
        429: "（触发限流）",
    }
    hint = hints.get(resp.status_code, "")
    if resp.status_code == 400 and "thinking" in detail:
        hint += "（当前模型可能不支持 thinking 参数）"
    return "HTTP {}：{}{}".format(resp.status_code, detail, hint)


def _call_once(review: str, api_key: str) -> dict:
    """调一次 API。返回 {ok, summary, note, reason, retryable, usage_str}。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT_TMPL.format(review=review)}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.1,
        # 关键：GLM-4.5 之后的模型默认开深度思考，思考过程同样消耗 max_tokens，
        # 32 个 token 会被思考吃光、正文一个 token 都分不到，content 返回空字符串。
        # 所以必须显式关闭思考。
        "thinking": {"type": "disabled"},
    }
    headers = {"Authorization": "Bearer {}".format(api_key)}
    result = {"ok": False, "summary": None, "note": "", "reason": "", "retryable": False, "usage_str": ""}
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        result["reason"] = "网络请求失败：{!r}".format(exc)
        result["retryable"] = True
        return result

    if resp.status_code != 200:
        result["reason"] = _describe_http_error(resp)
        result["retryable"] = resp.status_code == 429 or resp.status_code >= 500
        return result

    try:
        data = resp.json()
    except ValueError:
        result["reason"] = "HTTP 200 但响应不是 JSON：{!r}".format(resp.text[:200])
        return result

    if isinstance(data.get("error"), dict):  # 部分错误码也随 200 返回
        err = data["error"]
        result["reason"] = "API 返回错误 code={}, message={}".format(err.get("code"), err.get("message"))
        return result

    choices = data.get("choices") or []
    if not choices:
        result["reason"] = "响应中没有 choices：" + json.dumps(data, ensure_ascii=False)[:300]
        return result

    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    usage_str = "completion_tokens={}（预算{}），finish_reason={}".format(
        usage.get("completion_tokens"), MAX_TOKENS, finish_reason
    )
    reasoning = (message.get("reasoning_content") or "").strip()

    if not content:
        # 空内容的典型原因：思考没被关掉，预算全被 reasoning 消耗，正文 0 个 token
        if finish_reason == "length" and reasoning:
            result["reason"] = (
                "content 为空：max_tokens={} 的预算全部被深度思考消耗"
                "（已产生思考内容 {} 字，{}）。常见于思考未关闭或模型忽略了 thinking 参数。".format(
                    MAX_TOKENS, len(reasoning), usage_str
                )
            )
        elif finish_reason == "sensitive":
            result["reason"] = "content 为空：内容被安全审核拦截（{}）。".format(usage_str)
        else:
            result["reason"] = "content 为空（{}），message 原文：{}".format(
                usage_str, json.dumps(message, ensure_ascii=False)[:300]
            )
        return result

    result["ok"] = True
    result["summary"] = content
    result["usage_str"] = usage_str
    if finish_reason == "length":
        result["note"] = "触到 32 token 上限，摘要末尾可能被截断"
    elif finish_reason != "stop":
        result["note"] = "finish_reason={}，结果可能不完整".format(finish_reason)
    return result


def summarize(review: str, api_key: str) -> dict:
    """带重试的摘要：只重试网络错误/限流/5xx，业务失败如实返回。"""
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = _call_once(review, api_key)
        if result["ok"] or not result["retryable"]:
            return result
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)  # 简单退避
    result["reason"] = "重试 {} 次仍失败，最后原因：{}".format(MAX_ATTEMPTS, result["reason"])
    return result


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：环境变量 ZHIPUAI_API_KEY 未设置，无法调用 API。"
            "请先执行 export ZHIPUAI_API_KEY=你的Key 再运行。",
            file=sys.stderr,
        )
        return 1

    ok_count = 0
    for idx, review in enumerate(REVIEWS, 1):
        r = summarize(review, api_key)
        print("[{}/{}] 评论：{}".format(idx, len(REVIEWS), review))
        if r["ok"]:
            ok_count += 1
            suffix = "（{}）".format(r["note"]) if r["note"] else ""
            print("    摘要：{}{}".format(r["summary"], suffix))
            print("    预算：{}".format(r["usage_str"]))
        else:
            print("    ✗ 未拿到摘要，原因：{}".format(r["reason"]))
        print()

    failed = len(REVIEWS) - ok_count
    if failed:
        print(
            "结果：{}/{} 条拿到摘要，{} 条失败（原因见上），未用空结果冒充成功。".format(
                ok_count, len(REVIEWS), failed
            )
        )
        return 1
    print("结果：{}/{} 条全部成功，每条回复 token 均控制在 {} 以内。".format(len(REVIEWS), len(REVIEWS), MAX_TOKENS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
