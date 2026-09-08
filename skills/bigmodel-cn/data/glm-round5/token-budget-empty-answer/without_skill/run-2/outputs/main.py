#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 给商品评论各生成一句话摘要。

成本与预算控制：
- 每条请求 max_tokens=32，这是 API 侧的硬上限，回复不会超过 32 token；
- 显式传 thinking={"type": "disabled"} 关闭深度思考。GLM-4.5 及以上模型
  thinking 默认是 enabled，思考同样消耗输出 token 预算——在 32 token 的
  小预算下思维链很容易把额度耗光，返回 HTTP 200 但 content 是空字符串、
  finish_reason="length"，这是小预算场景最典型的"空回复"陷阱；
- 模型用 glm-4.5-flash（平台免费模型），评论量大时调用成本为零。

"真的拿到摘要文本"是硬要求：任何一条 content 为空或请求失败，都会把
具体原因（HTTP 状态 / 平台错误码 / finish_reason / 是否只剩思考内容）
打印出来并以非零码退出，绝不输出空字符串冒充完成。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.5-flash"  # 免费模型，GLM-4.5 系列，支持 thinking.type=disabled
MAX_TOKENS = 32          # 每条回复的 token 预算（max_tokens 为 API 侧硬上限）
MAX_RETRIES = 3
TIMEOUT = 60

COMMENTS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]

SYSTEM_PROMPT = (
    "你是商品评论摘要器：用一句不超过16个字的中文概括评论要点，优缺点都要提到。"
    "只输出摘要正文，不要引号、序号、前缀或任何解释。"
)

FINISH_REASON_HINTS = {
    "length": "回复在 32 token 预算内被截断（finish_reason=length）",
    "sensitive": "回复被平台内容安全审核拦截（finish_reason=sensitive）",
    "network_error": "模型推理异常（finish_reason=network_error）",
    "model_context_window_exceeded": "超出模型上下文窗口（finish_reason=model_context_window_exceeded）",
}


def call_glm(session, api_key, comment):
    """调用对话补全，带简单重试。返回 (resp, error)，error 为 None 表示请求已送达。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": comment},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.1,
        "thinking": {"type": "disabled"},  # 关键：防止思考耗尽 token 预算导致正文为空
    }

    last_error = "未知错误"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"网络请求异常（第 {attempt}/{MAX_RETRIES} 次）：{exc}"
            time.sleep(attempt)
            continue
        if resp.status_code in (429, 502, 503) and attempt < MAX_RETRIES:
            last_error = f"HTTP {resp.status_code}（第 {attempt}/{MAX_RETRIES} 次），稍后重试"
            time.sleep(attempt)
            continue
        return resp, None
    return None, last_error


def summarize(session, api_key, comment):
    """对单条评论做摘要。返回 (result, error)，二者互斥。

    result: {"text": 摘要文本, "tokens": completion_tokens}
    error:  拿不到摘要时的具体原因描述。
    """
    resp, error = call_glm(session, api_key, comment)
    if error:
        return None, error

    status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        return None, f"HTTP {status}，响应不是 JSON：{resp.text[:200]!r}"

    platform_error = body.get("error")
    if status != 200 or platform_error:
        if isinstance(platform_error, dict):
            code = platform_error.get("code")
            message = platform_error.get("message")
        else:
            code, message = platform_error, ""
        return None, f"HTTP {status}，平台错误码 {code}：{message}"

    choices = body.get("choices") or []
    if not choices:
        return None, f"HTTP 200 但响应中没有 choices：{json.dumps(body, ensure_ascii=False)[:300]}"

    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""
    finish_reason = choice.get("finish_reason")
    completion_tokens = (body.get("usage") or {}).get("completion_tokens")

    if content.strip():
        return {"text": content.strip(), "tokens": completion_tokens}, None

    # content 为空：绝不当作成功，把原因讲清楚
    parts = []
    if reasoning.strip():
        parts.append(
            f"模型只产出了思考内容、正文为空（思考耗尽了 {MAX_TOKENS} token 预算，"
            f"finish_reason={finish_reason}，reasoning_content 开头：{reasoning.strip()[:60]!r}）"
        )
    elif finish_reason in FINISH_REASON_HINTS:
        parts.append(FINISH_REASON_HINTS[finish_reason])
    elif finish_reason == "stop":
        parts.append("模型正常结束但 content 为空（finish_reason=stop）")
    else:
        parts.append(f"content 为空（finish_reason={finish_reason}）")
    if completion_tokens is not None:
        parts.append(f"completion_tokens={completion_tokens}/{MAX_TOKENS}")
    return None, "；".join(parts)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "未取得任何摘要：环境变量 ZHIPUAI_API_KEY 未设置。"
            "请先执行 export ZHIPUAI_API_KEY=<你的API Key> 再运行 python3 main.py。",
            file=sys.stderr,
        )
        return 1

    session = requests.Session()
    failures = 0
    for idx, comment in enumerate(COMMENTS, 1):
        result, error = summarize(session, api_key, comment)
        if result:
            print(f"[{idx}] 评论：{comment}")
            print(f"    摘要（completion_tokens={result['tokens']}/{MAX_TOKENS}）：{result['text']}")
        else:
            failures += 1
            print(f"[{idx}] 评论：{comment}", file=sys.stderr)
            print(f"    未取得摘要：{error}", file=sys.stderr)

    if failures:
        print(
            f"\n结果：{len(COMMENTS) - failures}/{len(COMMENTS)} 条成功，"
            f"{failures} 条未取得摘要，原因见上，未用空字符串顶替。",
            file=sys.stderr,
        )
        return 1
    print(f"\n结果：{len(COMMENTS)} 条摘要全部生成成功，每条回复 token 预算 ≤ {MAX_TOKENS}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
