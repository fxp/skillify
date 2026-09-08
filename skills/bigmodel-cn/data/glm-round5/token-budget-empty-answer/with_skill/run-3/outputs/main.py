#!/usr/bin/env python3
"""用智谱 GLM 给商品评论逐条生成一句话摘要（每条回复 token 预算 <= 32）。

用法:
    export ZHIPUAI_API_KEY=你的APIKey
    python3 main.py

选型说明（为什么是 glm-4.6 而不是 glm-5.3）:
  本任务的硬约束是 max_tokens=32。智谱 GLM-5.3 / GLM-5.3-Flash 在标准端点
  (https://open.bigmodel.cn/api/paas/v4) 强制开启深度思考，thinking.type=disabled
  会直接报业务错误 1210；而思考链同样消耗输出 token——32 的预算会被思维链先吃光，
  正文 content 为空、finish_reason=length。glm-4.6 属于"模型自动判断思考、可显式
  开关"的系列，thinking.type=disabled 是官方支持的取值，关闭后 32 token 全部留给
  摘要正文。（若想进一步压成本，可把 MODEL 换成免费的 glm-4.5-flash，同属可显式
  关闭思考的系列；不要用 glm-4.7 系列——强制思考，也不要用 glm-4-flash-250414
  ——不支持 thinking 参数。）

大批量场景提示: 同步接口的速率限制按并发数计算。评论量很大时，建议改用平台的
  Batch API 或异步对话接口（POST /paas/v4/async/chat/completions + 轮询
  GET /paas/v4/async-result/{id}），不占用同步并发额度。
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"
MAX_TOKENS = 32  # 每条回复的输出 token 硬预算（官方 schema 最小值 1，32 合法）
MAX_ATTEMPTS = 3  # 仅对 429/5xx/网络异常做指数退避重试
TIMEOUT = 60

SYSTEM_PROMPT = (
    "你是商品评论摘要助手。用一句不超过20个汉字的中文概括评论的核心观点，"
    "优点和缺点都要提到。直接输出摘要正文，不要加引号、序号、前缀或任何解释。"
)

REVIEWS = [
    "续航很顶，充一次用三天，但拍照实在一般，晚上噪点多",
    "客服态度好，物流也快，就是包装被压扁了一个角",
    "价格便宜是真便宜，做工也确实对得起这个价，别抱太高期望",
]


def extract_error_message(resp: requests.Response) -> str:
    """从错误响应体里取 error.code / error.message；取不到就返回原始文本片段。"""
    try:
        err = resp.json().get("error") or {}
        code = err.get("code", "?")
        message = err.get("message") or (resp.text or "")[:200]
        return f"业务错误码 {code}: {message}"
    except ValueError:
        return (resp.text or "")[:200] or "(空响应体)"


def call_chat_api(api_key: str, review: str) -> dict:
    """调用同步对话补全接口，返回解析后的 JSON。

    429（限流/过载）和 5xx 用指数退避重试；其余 4xx 属于鉴权/参数问题，
    重试没有意义，直接抛 RuntimeError 并携带具体原因。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": review},
        ],
        # 关键：显式关闭深度思考。max_tokens 只限制输出，但思考链也计入输出
        # token——开着思考时 32 的预算会被思维链耗尽，导致正文为空。
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_TOKENS,
        "temperature": 0.1,  # 摘要任务要稳定，压低随机性；只动 temperature 不动 top_p
    }

    last_error = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"网络请求异常: {exc}"
        else:
            if resp.status_code < 400:
                try:
                    return resp.json()
                except ValueError:
                    raise RuntimeError(
                        f"HTTP {resp.status_code} 但响应体不是合法 JSON: {(resp.text or '')[:200]}"
                    )
            last_error = f"HTTP {resp.status_code}: {extract_error_message(resp)}"
            if resp.status_code != 429 and resp.status_code < 500:
                raise RuntimeError(last_error)
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"重试 {MAX_ATTEMPTS} 次后仍失败，最后一次错误: {last_error}")


def extract_summary(data: dict) -> tuple[str | None, str]:
    """从响应里取摘要正文。

    返回 (摘要, 说明)。摘要为 None 时，说明里是拿不到摘要的具体原因——
    绝不把空字符串当成功结果返回。
    """
    if data.get("error"):
        err = data["error"]
        return None, f"接口返回业务错误 {err.get('code')}: {err.get('message')}"

    choices = data.get("choices") or []
    if not choices:
        snippet = json.dumps(data, ensure_ascii=False)[:300]
        return None, f"响应里没有 choices 字段: {snippet}"

    choice = choices[0]
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason", "?")
    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")

    content = (message.get("content") or "").strip()
    if not content:
        reasoning = (message.get("reasoning_content") or "").strip()
        if finish_reason == "length":
            reason = (
                f"输出在 {MAX_TOKENS} token 预算内被截断，且没有生成任何正文 "
                f"(finish_reason=length)"
            )
            if reasoning:
                reason += "；思考链消耗了预算（reasoning_content 非空），请确认 thinking 已关闭"
            return None, reason
        if finish_reason == "sensitive":
            return None, "内容被平台安全策略拦截 (finish_reason=sensitive)"
        if finish_reason == "network_error":
            return None, "模型推理异常 (finish_reason=network_error)"
        return None, f"content 为空，finish_reason={finish_reason}"

    note = f"输出 {completion_tokens} tokens / 预算 {MAX_TOKENS}, finish_reason={finish_reason}"
    if completion_tokens is not None and completion_tokens > MAX_TOKENS:
        note += "（实际输出超出预算，需要检查）"
    if finish_reason == "length":
        note += "（达到预算上限，摘要可能被截断）"
    return content, note


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        print("请先执行: export ZHIPUAI_API_KEY=你的APIKey", file=sys.stderr)
        return 1

    failures = 0
    for idx, review in enumerate(REVIEWS, 1):
        print(f"[{idx}] 评论: {review}")
        try:
            data = call_chat_api(api_key, review)
        except RuntimeError as exc:
            print(f"    失败: API 调用未成功 —— {exc}")
            failures += 1
            continue

        summary, note = extract_summary(data)
        if summary is None:
            print(f"    失败: 未拿到摘要 —— {note}")
            failures += 1
        else:
            print(f"    摘要: {summary}")
            print(f"    ({note})")

    print()
    if failures:
        print(f"结果: {len(REVIEWS) - failures}/{len(REVIEWS)} 条成功，{failures} 条失败（原因见上）。")
        return 1
    print(f"结果: 全部 {len(REVIEWS)} 条评论均拿到摘要，每条输出 token 控制在 {MAX_TOKENS} 预算内。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
