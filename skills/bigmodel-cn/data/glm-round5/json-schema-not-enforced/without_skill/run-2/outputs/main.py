#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类（仅依赖 requests）。

输出契约（结果直接入库，所以由代码保证、不靠模型自觉）：
    stdout 每行一个 JSON 对象，与 TEXTS 顺序一一对应，形如
        {"sentiment": "正面", "score": 0.92}
    - sentiment 只能是 "正面"/"负面"/"中性" 三者之一
    - score 是 0 到 1 之间的数字
    - 输出对象由本脚本重新构造，字段集合固定，模型多吐的字段不会进入输出

可靠性设计：GLM 的 response_format 只支持 json_object（保证是合法 JSON），
不保证符合 schema，所以每条输出都在代码里严格校验；不合法就把原因反馈给
模型重试，重试耗尽则整体以非零码退出、不输出任何半成品，避免脏数据入库。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
可选环境变量：
    GLM_MODEL  覆盖默认模型（默认 glm-4.7-flash，智谱当前免费文本模型）
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.7-flash"
MODEL = os.environ.get("GLM_MODEL", DEFAULT_MODEL)
API_KEY_ENV = "ZHIPUAI_API_KEY"

MAX_ATTEMPTS = 3            # 单条文本最多请求次数（含"输出不合格重新问"）
HTTP_RETRY_DELAYS = (1, 2, 4)  # 网络异常/限流/5xx 的退避重试间隔（秒）
REQUEST_TIMEOUT = 60

VALID_SENTIMENTS = ("正面", "负面", "中性")

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是一个情感分类器，只输出 JSON，不输出任何其他文字。"
    "对用户给出的文本判断情感倾向，输出一个 JSON 对象，包含且仅包含两个字段："
    '"sentiment"：字符串，只能是 "正面"、"负面"、"中性" 三者之一；'
    '"score"：数字，表示该分类的置信度，取值 0 到 1 之间（例如 0.87）。'
    "不要输出解释，不要用 Markdown 代码块包裹。"
)


class GlmApiError(RuntimeError):
    """调用 GLM 接口失败（鉴权、参数、服务端错误重试耗尽等）。"""


class SchemaError(RuntimeError):
    """模型输出不符合约定结构（重试耗尽）。"""


def _post_chat(api_key, messages):
    """调用对话补全接口，返回模型输出文本（choices[0].message.content）。

    网络异常、429、5xx 按退避间隔重试；其余 4xx（鉴权失败、参数错误等）
    重试无意义，直接抛 GlmApiError。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    last_error = None
    for delay in (0,) + HTTP_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            resp = requests.post(
                API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = exc
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                raise GlmApiError(f"接口返回了非 JSON 内容：{resp.text[:500]}")
            if data.get("error"):
                raise GlmApiError(
                    "接口返回错误：" + json.dumps(data["error"], ensure_ascii=False)
                )
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                raise GlmApiError(
                    f"接口响应结构异常：{json.dumps(data, ensure_ascii=False)[:500]}"
                )
            if not isinstance(content, str) or not content.strip():
                raise GlmApiError(
                    f"模型返回内容为空（可能被内容安全策略拦截）："
                    f"{json.dumps(data, ensure_ascii=False)[:500]}"
                )
            return content

        body = resp.text[:500]
        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = GlmApiError(f"HTTP {resp.status_code}: {body}")
            continue
        # 400/401/403 等客户端错误，重试不会好转
        raise GlmApiError(f"HTTP {resp.status_code}: {body}")

    raise GlmApiError(
        f"请求失败（已重试 {len(HTTP_RETRY_DELAYS)} 次）：{last_error}"
    )


def _extract_json(content):
    """从模型输出中解析出 JSON；容忍 markdown 围栏或前后多余文字。"""
    text = content.strip()

    stripped = text
    if stripped.startswith("```"):  # 去掉 ``` 或 ```json 围栏
        newline = stripped.find("\n")
        stripped = stripped[newline + 1:] if newline != -1 else stripped.strip("`")
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]

    for candidate in (text, stripped):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    for candidate in (stripped, text):  # 兜底：截取第一个 { 到最后一个 }
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("无法从模型输出中解析出 JSON")


def _validate(obj):
    """校验模型输出，返回 (归一化结果, 不合格原因)，二者其一为 None。

    返回的结果对象在这里重新构造，字段名和字段集合由代码保证；
    score 拒绝布尔值、字符串数字会转 float、超出 [0,1] 一律不合格。
    """
    if not isinstance(obj, dict):
        return None, "输出不是一个 JSON 对象"
    if "sentiment" not in obj or "score" not in obj:
        return None, '缺少字段，必须且只能有 "sentiment" 和 "score"'

    sentiment = obj["sentiment"]
    if isinstance(sentiment, str):
        sentiment = sentiment.strip()
    if sentiment not in VALID_SENTIMENTS:
        return None, (
            f'"sentiment" 只能是 {"、".join(VALID_SENTIMENTS)}，'
            f"实际是 {sentiment!r}"
        )

    raw_score = obj["score"]
    if isinstance(raw_score, bool):  # bool 是 int 的子类，要先排除
        return None, '"score" 必须是数字，不能是布尔值'
    if isinstance(raw_score, (int, float)):
        score = float(raw_score)
    elif isinstance(raw_score, str):
        try:
            score = float(raw_score.strip())
        except ValueError:
            return None, f'"score" 必须是数字，实际是 {raw_score!r}'
    else:
        return None, f'"score" 必须是数字，实际是 {raw_score!r}'
    if not 0.0 <= score <= 1.0:
        return None, f'"score" 必须在 0 到 1 之间，实际是 {score}'

    return {"sentiment": sentiment, "score": round(score, 4)}, None


def classify(api_key, text):
    """对单条文本做情感分类，返回严格符合输出契约的 dict。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    last_reason = None
    for _ in range(MAX_ATTEMPTS):
        content = _post_chat(api_key, messages)
        try:
            obj = _extract_json(content)
        except ValueError as exc:
            last_reason = f"{exc}（原始输出：{content[:200]!r}）"
        else:
            result, reason = _validate(obj)
            if result is not None:
                return result
            last_reason = reason
        # 把不合格原因反馈给模型，从原始问答重新追问一次
        messages = messages[:2] + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    f"上面的输出不符合要求：{last_reason}。"
                    "请重新输出，只输出一个 JSON 对象："
                    '{"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}'
                ),
            },
        ]
    raise SchemaError(f"重试 {MAX_ATTEMPTS} 次后输出仍不合格：{last_reason}")


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        print(f"错误：请先设置环境变量 {API_KEY_ENV}（智谱开放平台 API Key）",
              file=sys.stderr)
        return 1

    # 先全部分类成功，再统一输出：任何一条失败都不产出半成品
    try:
        results = [classify(api_key, text) for text in TEXTS]
    except (GlmApiError, SchemaError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # stderr 打印原文便于人工核对；stdout 只输出严格结构，可直接入库
    for text, result in zip(TEXTS, results):
        print(f"{text} -> {json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
