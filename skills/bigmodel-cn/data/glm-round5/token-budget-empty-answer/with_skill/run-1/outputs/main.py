#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 给商品评论各生成一句话摘要（每条回复输出 token 预算 <= 32）。

模型选型说明（这是本脚本能否拿到非空摘要的关键）：
  max_tokens 只限制输出侧，而开启深度思考时思维链 token 同样计入输出预算。
  glm-5.3 / glm-5.3-flash 在标准端点强制思考（thinking.type=disabled 会报
  业务错误 1210），32 个 token 会被思维链耗尽，最终 content 为空、
  finish_reason=length——即"预算很小却拿到空回复"的典型坑。
  glm-5.2 属于"模型自动判断是否思考"的系列，官方文档明确支持
  thinking.type=disabled；显式关闭后 32 个 token 全部留给可见正文，
  才能稳定拿到摘要文本，同时压住成本。

失败处理约定：
  任何一条评论没拿到摘要文本，都会打印明确原因（HTTP/业务错误码、
  finish_reason、usage 细节），进程以非零码退出；绝不打印空字符串冒充完成。
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY_ENV = "ZHIPUAI_API_KEY"
MODEL = "glm-5.2"
MAX_TOKENS = 32  # 每条回复的输出 token 预算上限（官方 max_tokens 最小值为 1，32 合法）
MAX_RETRIES = 3  # 仅 429/5xx/网络异常重试；4xx 配置类错误重试无意义
RETRY_BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT = 60

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

# system 提示词对全部评论保持逐字一致：固定前缀可命中平台的隐式上下文缓存，
# 命中部分按优惠价计费（约为标准价 50%），评论量大时能进一步压成本。
SYSTEM_PROMPT = (
    "你是商品评论摘要助手。对给出的评论输出一句话摘要："
    "15 个字以内，不带引号和序号，不要任何解释或前缀，直接输出摘要文本。"
)


def call_glm(api_key, review):
    """对单条评论请求一次 GLM。返回 (响应 dict, 失败原因或 None)。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "评论：" + review},
        ],
        "thinking": {"type": "disabled"},  # 关键：关闭思维链，32 token 预算全部留给正文
        "max_tokens": MAX_TOKENS,
        "do_sample": False,  # 贪心解码、输出稳定，批量场景可控（此时 temperature/top_p 被忽略）
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    reason = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            reason = "网络请求失败（第 %d/%d 次）: %s: %s" % (attempt, MAX_RETRIES, type(exc).__name__, exc)
        else:
            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json()
                except ValueError:
                    return None, "HTTP %d 但响应体不是合法 JSON: %r" % (resp.status_code, resp.text[:200])
                err = data.get("error")
                if isinstance(err, dict):  # 防御：个别业务错误可能随 2xx 返回
                    return None, "API 业务错误: code=%s message=%s" % (err.get("code"), err.get("message"))
                return data, None
            try:
                err = (resp.json() or {}).get("error") or {}
                detail = "code=%s message=%s" % (err.get("code"), err.get("message"))
            except ValueError:
                detail = resp.text[:200]
            reason = "HTTP %d: %s（第 %d/%d 次）" % (resp.status_code, detail, attempt, MAX_RETRIES)
            if resp.status_code != 429 and resp.status_code < 500:
                return None, "HTTP %d: %s" % (resp.status_code, detail)  # 4xx 配置错误，重试无意义
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))  # 指数退避，避免高频重试加重限流
    return None, "重试 %d 次后仍失败，最后一次原因: %s" % (MAX_RETRIES, reason)


def extract_summary(data):
    """从响应中取出摘要文本。

    返回 ((摘要文本, finish_reason, usage), None) 或 (None, 失败原因)。
    content 为空时绝不静默当作成功，逐项给出可定位的原因。
    """
    choices = data.get("choices") or []
    if not choices:
        return None, "响应缺少 choices 字段: " + str(data)[:300]
    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}

    if content:
        return (content, finish_reason, usage), None

    # 走到这里说明 200 OK 但没拿到正文：把原因说清楚，而不是打印空字符串
    detail = usage.get("completion_tokens_details") or {}
    reasoning_text = message.get("reasoning_content") or ""
    facts = (
        "finish_reason=%s, completion_tokens=%s, reasoning_tokens=%s, reasoning_content长度=%d"
        % (finish_reason, usage.get("completion_tokens"), detail.get("reasoning_tokens", "字段未返回"),
           len(reasoning_text))
    )
    if finish_reason == "length":
        why = "达到 max_tokens=%d 上限且没有任何可见正文：输出预算在正文开始前就被耗尽" % MAX_TOKENS
        if reasoning_text or (detail.get("reasoning_tokens") or 0):
            why += "；思维链非空，说明预算被思考吃掉——本脚本已显式关闭 thinking，若复现请核实平台行为是否变化"
    elif finish_reason == "sensitive":
        why = "触发内容安全拦截，该条评论被平台判定为敏感"
    elif finish_reason == "network_error":
        why = "模型推理异常（network_error）"
    elif message.get("tool_calls"):
        why = "模型返回了 tool_calls 而非文本（本请求未传工具，属未预期行为）"
    else:
        why = "未预期的响应结构, message 字段: " + str(message)[:300]
    return None, "API 返回 200 但摘要文本为空（%s；%s）" % (why, facts)


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print("[错误] 未读取到环境变量 %s，无法调用智谱 API。" % API_KEY_ENV)
        print("       请先执行: export %s=<你的智谱 API Key>，再运行 python3 main.py" % API_KEY_ENV)
        return 1

    failures = 0
    for idx, review in enumerate(REVIEWS, 1):
        print("[%d] 评论: %s" % (idx, review))
        data, err = call_glm(api_key, review)
        result = None
        if err is None:
            result, err = extract_summary(data)
        if err is not None:
            failures += 1
            print("    未拿到摘要，原因: %s" % err)
            print()
            continue

        summary, finish_reason, usage = result
        completion = usage.get("completion_tokens", "?")
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        budget_note = "输出 %s/%d token（含思考 %s）" % (completion, MAX_TOKENS, reasoning)
        if finish_reason == "length":
            budget_note += "；注意 finish_reason=length，正文在预算上限处被截断"
        print("    摘要: %s" % summary)
        print("    （finish_reason=%s, %s）" % (finish_reason, budget_note))
        print()

    if failures:
        print("结束：%d/%d 条成功，%d 条未拿到摘要（原因见上），失败项没有输出空文本。" % (
            len(REVIEWS) - failures, len(REVIEWS), failures))
        return 1
    print("结束：%d/%d 条摘要全部成功获取，每条输出 token 均未超过 %d。" % (len(REVIEWS), len(REVIEWS), MAX_TOKENS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
