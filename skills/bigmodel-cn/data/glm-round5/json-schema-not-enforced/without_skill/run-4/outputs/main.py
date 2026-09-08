#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱 GLM 对文本做情感分类，结果直接入库，输出必须严格符合：
    {"sentiment": "正面" | "负面" | "中性", "score": 0到1之间的数字}

- API Key 从环境变量 ZHIPUAI_API_KEY 读取
- 仅依赖第三方库 requests
- 可用环境变量 GLM_MODEL 覆盖模型（默认 glm-4.5-flash）
- 输出：stdout 逐行打印 JSON（JSON Lines），顺序与输入文本一致；
  只有 3 条全部分类成功才会输出，避免部分结果入库。
- 模型输出会在本地做严格校验与归一化（字段名、取值范围），
  校验失败自动重试；重试耗尽则报错退出（退出码 1），绝不输出脏数据。
"""

import json
import math
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-4.5-flash")
MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 60

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

# 模型可能出现的同义写法，统一映射成三个合法取值
SENTIMENT_ALIASES = {
    "正面": "正面", "负面": "负面", "中性": "中性",
    "积极": "正面", "消极": "负面",
    "positive": "正面", "negative": "负面", "neutral": "中性",
}

SYSTEM_PROMPT = (
    "你是情感分类器。对用户提供的文本判断情感倾向，只输出一个 JSON 对象，"
    '格式严格为 {"sentiment": "正面"|"负面"|"中性", "score": <0到1的数字>}。\n'
    "规则：\n"
    "1. sentiment 只能取值：正面、负面、中性（中文，不要用英文或其他说法）。\n"
    "2. score 是 0 到 1 之间的置信度数字，例如 0.87；不要百分数，不要字符串。\n"
    "3. 除这个 JSON 对象外不要输出任何其他内容（不要解释、不要 markdown 代码块）。"
)


class FatalError(Exception):
    """不可重试的错误（如 API Key 无效）"""


def extract_json_object(raw):
    """从模型返回的文本里解析出 JSON 对象，容忍 markdown 围栏和前后杂文字。"""
    text = (raw or "").strip()
    if text.startswith("```"):  # 去掉 ```json ... ``` 围栏
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    raise ValueError(f"无法从模型输出中解析出 JSON：{raw!r}")


def normalize_record(parsed):
    """校验并归一化成严格的 {"sentiment", "score"}；不合法则抛 ValueError。"""
    if not isinstance(parsed, dict):
        raise ValueError("模型输出不是 JSON 对象")
    if "sentiment" not in parsed or "score" not in parsed:
        raise ValueError(f"缺少必需字段，实际字段：{sorted(parsed.keys())}")

    raw_sentiment = parsed["sentiment"]
    sentiment = SENTIMENT_ALIASES.get(
        raw_sentiment.strip() if isinstance(raw_sentiment, str) else None
    )
    if sentiment is None:
        raise ValueError(f"sentiment 取值非法：{raw_sentiment!r}")

    score = parsed["score"]
    if isinstance(score, bool):  # bool 是 int 的子类，先排除
        raise ValueError("score 不能是布尔值")
    if isinstance(score, str):
        try:
            score = float(score.strip())
        except ValueError:
            raise ValueError(f"score 不是数字：{score!r}")
    if not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError(f"score 不是数字：{score!r}")
    score = float(score)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score 不在 [0, 1] 区间：{score}")

    return {"sentiment": sentiment, "score": round(score, 4)}


def classify_sentiment(text, api_key):
    """对单条文本做情感分类，返回严格校验后的 dict；失败到底则抛异常。"""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(2 ** (attempt - 1))  # 1s、2s 退避
        try:
            response = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                    "thinking": {"type": "disabled"},  # 简单分类任务，关掉思考过程
                    "response_format": {"type": "json_object"},
                },
                timeout=TIMEOUT_SECONDS,
            )
            if response.status_code in (401, 403):
                raise FatalError(
                    f"API Key 无效或无权限（HTTP {response.status_code}）：{response.text[:200]}"
                )
            if response.status_code >= 400:  # 429/5xx 等可重试
                raise RuntimeError(f"HTTP {response.status_code}：{response.text[:200]}")
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"响应里没有 choices：{json.dumps(data, ensure_ascii=False)[:200]}")
            content = (choices[0].get("message") or {}).get("content")
            if not content:
                raise RuntimeError(
                    f"模型没有返回内容（finish_reason={choices[0].get('finish_reason')}）"
                )
            return normalize_record(extract_json_object(content))
        except FatalError:
            raise
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc
            print(f"[重试 {attempt}/{MAX_ATTEMPTS}] {text!r} 分类失败：{exc}", file=sys.stderr)
    raise RuntimeError(f"重试 {MAX_ATTEMPTS} 次后仍失败：{text!r}，最后错误：{last_error}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=<你的Key>",
              file=sys.stderr)
        return 1

    results = []
    try:
        for text in TEXTS:
            results.append(classify_sentiment(text, api_key))
    except (FatalError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # 全部成功才统一输出，顺序与输入文本一致
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
