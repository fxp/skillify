#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 给 3 条商品评论各生成一句话摘要。

成本与预算：
    - 模型默认 glm-4.5-flash（智谱免费档），可用环境变量 GLM_MODEL 覆盖；
    - 每条回复的输出 token 预算硬上限 MAX_TOKENS=32，通过 max_tokens 参数
      在服务端直接封顶，单条回复的 completion_tokens 不会超过 32。

空回复防护（小 token 预算下最常见的坑）：
    - GLM-4.5 及以上系列默认开启深度思考，思维链与正文共用 max_tokens 预算；
      预算只有 32 时往往全被思考吃掉，最终返回的 content 是空字符串。
      因此请求里显式传 thinking={"type": "disabled"} 关闭思考。
    - 任何情况拿不到摘要文本（网络错误、HTTP/API 错误、content 为空、被风控
      拦截等）都会打印具体原因并以非 0 退出码结束，绝不拿空字符串冒充成功。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-4.5-flash")
MAX_TOKENS = 32  # 每条回复的 token 预算上限（服务端强制执行）
TIMEOUT = 30  # 单次请求超时（秒）
MAX_RETRIES = 3  # 网络/限流/服务端错误的总尝试次数

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

SYSTEM_PROMPT = (
    "你是商品评论摘要助手。只输出摘要本身：一句话，20字以内，"
    "同时点到优点和缺点，不要引号、前缀或任何解释。"
)


class SummaryError(Exception):
    """拿不到摘要文本；message 里必须写清具体原因。"""


def _api_error_text(resp):
    """把非 200 响应整理成可读的错误描述。"""
    try:
        err = (resp.json() or {}).get("error") or {}
    except ValueError:
        err = {}
    parts = ["HTTP %d" % resp.status_code]
    if err.get("code") is not None and err["code"] != "":
        parts.append("code=%s" % err["code"])
    if err.get("message"):
        parts.append("message=%s" % err["message"])
    else:
        snippet = resp.text.strip().replace("\n", " ")[:200]
        if snippet:
            parts.append("body=%s" % snippet)
    return "，".join(parts)


def _request_once(session, api_key, review):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请概括这条商品评论：%s" % review},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.1,
        # 关键：关闭深度思考。思考模型会把 32 个 token 的预算先花在思维链上，
        # 导致正文 content 为空（reasoning_content 反而有内容）。
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    return session.post(
        API_URL,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )


def _parse_success(resp):
    """解析 HTTP 200 的响应；拿不到非空正文时抛出带明确原因的 SummaryError。"""
    try:
        data = resp.json()
    except ValueError:
        raise SummaryError("HTTP 200 但响应体不是 JSON：%r" % resp.text[:200])

    choices = data.get("choices") or []
    if not choices:
        raise SummaryError(
            "HTTP 200 但响应中没有 choices：%s"
            % json.dumps(data, ensure_ascii=False)[:300]
        )

    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}

    if not content:
        # 每一种"拿不到正文"的情况都给出明确原因，绝不返回空字符串。
        if reasoning:
            raise SummaryError(
                "content 为空：模型输出了思维链（reasoning_content 非空，"
                "finish_reason=%s），32 token 预算被深度思考耗尽。"
                "请确认请求已带 thinking.type=disabled，或改用可关闭思考的模型。"
                % finish_reason
            )
        if finish_reason == "length":
            raise SummaryError(
                "content 为空且 finish_reason=length：输出在正文第一个 token "
                "生成之前就触达 32 token 上限（通常也是思维链先消耗预算所致）。"
            )
        if finish_reason == "sensitive":
            raise SummaryError(
                "content 为空：内容被安全策略拦截（finish_reason=sensitive）。"
            )
        raise SummaryError(
            "content 为空：finish_reason=%s，message 字段=%s"
            % (finish_reason, json.dumps(message, ensure_ascii=False)[:300])
        )

    return {
        "content": content,
        "finish_reason": finish_reason,
        "completion_tokens": usage.get("completion_tokens"),
    }


def summarize(session, api_key, review):
    """调一次 GLM 生成摘要，成功返回 dict，失败抛 SummaryError（含原因）。"""
    last_reason = "未知错误"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _request_once(session, api_key, review)
        except requests.RequestException as exc:
            last_reason = "网络请求失败：%r" % exc
        else:
            if resp.status_code == 200:
                return _parse_success(resp)
            reason = _api_error_text(resp)
            # 401 鉴权失败、400 参数错误这类重试也没用，直接失败；
            # 429 限流和 5xx 服务端抖动才值得重试。
            if resp.status_code != 429 and resp.status_code < 500:
                raise SummaryError(reason)
            last_reason = reason
        if attempt < MAX_RETRIES:
            time.sleep(attempt)  # 线性退避：1s、2s
    raise SummaryError(
        "重试 %d 次后仍失败，最后原因：%s" % (MAX_RETRIES, last_reason)
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "失败：环境变量 ZHIPUAI_API_KEY 未设置，没有 Key 无法调用智谱 API。\n"
            "      请先执行：export ZHIPUAI_API_KEY=你的Key，再运行 python3 main.py",
            file=sys.stderr,
        )
        return 2

    print("模型：%s，每条回复 token 预算：%d\n" % (MODEL, MAX_TOKENS))
    session = requests.Session()
    succeeded = 0
    for index, review in enumerate(REVIEWS, 1):
        print("[%d] 原文：%s" % (index, review))
        try:
            result = summarize(session, api_key, review)
        except SummaryError as exc:
            print("    未拿到摘要，原因：%s\n" % exc)
            continue
        note = "finish_reason=%s" % result["finish_reason"]
        if result["completion_tokens"] is not None:
            note += "，completion_tokens=%s/%d" % (
                result["completion_tokens"],
                MAX_TOKENS,
            )
        print("    摘要：%s" % result["content"])
        print("    （%s）\n" % note)
        succeeded += 1

    if succeeded == len(REVIEWS):
        print("完成：%d/%d 条评论全部拿到摘要。" % (succeeded, len(REVIEWS)))
        return 0
    print(
        "完成：%d/%d 条成功；失败各条的原因见上，未拿到摘要的不会用空字符串代替。"
        % (succeeded, len(REVIEWS))
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
