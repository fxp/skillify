#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类。

输出（stdout，每行一个 JSON，顺序与 TEXTS 一致）严格符合：
    {"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}

注意：GLM 的 response_format 没有服务端强 Schema 约束（json_schema 会被静默忽略，
json_object 也只是弱约束），字段合法性由本脚本做客户端校验 + 失败重试兜底，
校验始终不过就直接报错退出，保证不产出脏数据。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests + 标准库。
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")
# 模型偶发用英文作答时的归一化映射，避免英文值直接入库
SENTIMENT_ALIASES = {
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "pos": "正面",
    "neg": "负面",
    "neu": "中性",
}
MAX_ATTEMPTS = 3

SYSTEM_PROMPT = (
    "你是情感分类引擎。对用户给出的文本做情感分类，只输出一个 JSON 对象，"
    "不要输出任何解释、markdown 代码块或其他文字。JSON 必须严格符合：\n"
    '{"sentiment": "正面" | "负面" | "中性", "score": 0到1之间的小数}\n'
    '字段名一字不能差；sentiment 只能取"正面"、"负面"、"中性"三个中文值之一，'
    "不要用 positive/negative/neutral 等英文；score 是 0 到 1 之间的小数，"
    "表示该分类的置信度。只允许这两个字段，不要新增字段。"
)


class _ClassifyError(Exception):
    """一次分类尝试失败。retryable=False 时（如鉴权错误）不再重试。"""

    def __init__(self, message, retryable):
        super().__init__(message)
        self.retryable = retryable


def _classify_once(text, api_key):
    """调一次 API 并完成解析与校验，失败抛 _ClassifyError。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"待分类文本：{text}"},
        ],
        # 平台无 strict json_schema，用 json_object 弱约束 + prompt 写死结构
        "response_format": {"type": "json_object"},
        # glm-5.3 在标准端点强制思考、思考 token 计入 max_tokens：
        # 调低思考强度并给足预算，避免 content 被 thinking 吃空
        "reasoning_effort": "low",
        "max_tokens": 2048,
        "temperature": 0.1,
    }
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=(10, 120),
        )
    except requests.RequestException as e:
        raise _ClassifyError(f"网络错误: {e}", retryable=True)

    if resp.status_code != 200:
        retryable = resp.status_code == 429 or resp.status_code >= 500
        try:
            err = resp.json().get("error", {})
            detail = f"{err.get('code', '')} {err.get('message', '')}".strip()
        except ValueError:
            detail = resp.text[:200]
        raise _ClassifyError(f"HTTP {resp.status_code}: {detail}", retryable=retryable)

    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    # finish_reason=length 意味着输出（含思考 token）被截断，content 可能为空或残缺
    finish_reason = choice.get("finish_reason")
    if finish_reason != "stop":
        raise _ClassifyError(
            f"finish_reason={finish_reason!r}（非 stop，输出可能被截断）", retryable=True
        )
    content = (choice.get("message") or {}).get("content") or ""
    if not content.strip():
        raise _ClassifyError("content 为空", retryable=True)
    return _validate(_extract_json(content))


def _extract_json(content):
    """从模型输出提取 JSON 对象，容忍偶发的代码块包裹或夹带解释文字。"""
    s = content.strip()
    if not (s.startswith("{") and s.endswith("}")):
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start:
            raise _ClassifyError(f"输出中找不到 JSON 对象: {content[:100]!r}", retryable=True)
        s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise _ClassifyError(f"JSON 解析失败: {e}; 原文: {content[:100]!r}", retryable=True)


def _validate(obj):
    """把模型输出整形成入库结构；无法整形的直接判失败触发重试。"""
    if not isinstance(obj, dict):
        raise _ClassifyError(f"输出不是 JSON 对象: {obj!r}", retryable=True)
    if "sentiment" not in obj or "score" not in obj:
        raise _ClassifyError(f"缺少 sentiment/score 字段: {obj!r}", retryable=True)

    sentiment = obj["sentiment"]
    if not isinstance(sentiment, str):
        raise _ClassifyError(f"sentiment 不是字符串: {sentiment!r}", retryable=True)
    sentiment = sentiment.strip().strip("\"'").strip()
    if sentiment in VALID_SENTIMENTS:
        norm = sentiment
    else:
        norm = SENTIMENT_ALIASES.get(sentiment) or SENTIMENT_ALIASES.get(sentiment.lower())
        if norm is None:
            raise _ClassifyError(f"sentiment 取值非法: {sentiment!r}", retryable=True)

    raw = obj["score"]
    if isinstance(raw, bool):  # bool 是 int 子类，先排除
        raise _ClassifyError(f"score 是布尔值: {raw!r}", retryable=True)
    try:
        score = float(raw)
    except (TypeError, ValueError):
        raise _ClassifyError(f"score 不是数字: {raw!r}", retryable=True)
    if not 0.0 <= score <= 1.0:
        clamped = min(max(score, 0.0), 1.0)
        print(
            f"[normalize] score={score!r} 超出 [0,1]，已夹取为 {clamped}",
            file=sys.stderr,
        )
        score = clamped

    # 只保留约定的两个字段，多余字段丢弃，保证入库结构唯一
    return {"sentiment": norm, "score": round(score, 4)}


def classify(text, api_key):
    """对单条文本分类，带重试；始终失败则抛 RuntimeError（宁可不写也不写脏数据）。"""
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _classify_once(text, api_key)
        except _ClassifyError as e:
            last = e
            print(f"[{attempt}/{MAX_ATTEMPTS}] 文本 {text!r} 失败: {e}", file=sys.stderr)
            if not e.retryable:
                break
            time.sleep(2 * attempt)  # 简单退避，避开瞬时限流
    raise RuntimeError(f"文本 {text!r} 未得到合法分类结果（尝试 {MAX_ATTEMPTS} 次）: {last}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1
    for text in TEXTS:
        result = classify(text, api_key)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
