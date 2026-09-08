#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 做情感分类。

每条文本输出一行严格符合下游入库约束的 JSON：
    {"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}

智谱 API 的 response_format 只保证"是合法 JSON"，不校验 schema，
所以字段名和取值约束由本脚本在 validate() 里硬校验：
不合格的输出会带着错误反馈重试，重试耗尽则报错退出——宁可失败，不产脏数据。

用法：
    export ZHIPUAI_API_KEY=你的key
    python3 main.py
"""

import json
import math
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 免费文本模型，可用环境变量 ZHIPUAI_MODEL 覆盖（须为支持 thinking 参数的 GLM-4.5+ 文本模型）
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.7-flash")
MAX_ATTEMPTS = 3
TIMEOUT = 60

VALID_SENTIMENTS = ("正面", "负面", "中性")

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的文本判断整体情感倾向，"
    "只输出一个 JSON 对象，不要输出任何解释、前后缀或代码块标记。"
    "JSON 必须恰好包含两个字段："
    '"sentiment"，只能是 "正面"、"负面"、"中性" 三者之一；'
    '"score"，0 到 1 之间的数字，表示该判断的置信度，越接近 1 越确定。'
    "字段名和取值范围都不能偏离。"
)


class FatalError(RuntimeError):
    """重试也无济于病的错误（如 Key 无效），直接终止。"""


def call_glm(api_key: str, messages: list) -> str:
    """调用智谱对话补全接口，返回模型输出的原始文本。"""
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.1,  # 分类任务要稳定，温度压低
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},  # 纯分类不需要思维链
        },
        timeout=TIMEOUT,
    )
    if resp.status_code in (401, 403):
        raise FatalError(
            f"ZHIPUAI_API_KEY 无效或无权限（HTTP {resp.status_code}）: {resp.text[:200]}"
        )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"API 返回中没有 choices: {json.dumps(data, ensure_ascii=False)[:300]}")
    content = (choices[0].get("message") or {}).get("content") or ""
    content = content.strip()
    if not content:
        raise RuntimeError(f"API 返回的 content 为空: {json.dumps(choices[0], ensure_ascii=False)[:300]}")
    return content


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象，容忍 ```json 围栏或前后多余文字。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"输出中找不到 JSON 对象: {text!r}")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 顶层不是对象: {text!r}")
    return obj


def validate(result: dict) -> dict:
    """按入库约束硬校验并归一化，任何不符都抛 ValueError 触发重试。"""
    if set(result) != {"sentiment", "score"}:
        raise ValueError(f"字段名不符，必须恰好是 sentiment/score: {sorted(result)}")
    sentiment = result["sentiment"]
    if sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"sentiment 只能是 {'/'.join(VALID_SENTIMENTS)}，得到: {sentiment!r}")
    score = result["score"]
    if isinstance(score, bool):  # bool 是 int 子类，先排除
        raise ValueError(f"score 不能是布尔值: {score!r}")
    try:
        score = float(score)
    except (TypeError, ValueError):
        raise ValueError(f"score 必须是数字: {score!r}")
    if not math.isfinite(score):
        raise ValueError(f"score 必须是有限数字: {score!r}")
    # 轻微越界（如 1.02）夹回 [0,1]，保证入库约束不被破坏
    return {"sentiment": sentiment, "score": round(min(max(score, 0.0), 1.0), 4)}


def classify_one(api_key: str, text: str) -> dict:
    """对单条文本分类：调用 -> 提取 -> 校验，失败带反馈重试。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"待分类文本：{text}"},
    ]
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        raw = None
        try:
            raw = call_glm(api_key, messages)
            return validate(extract_json(raw))
        except FatalError:
            raise
        except Exception as exc:  # 网络/解析/校验失败，带着错误反馈重试
            last_error = exc
            followup = {
                "role": "user",
                "content": (
                    f"你上次的输出不符合要求（错误：{exc}）。"
                    "请重新只输出一个 JSON 对象，"
                    '必须恰好是 {"sentiment": "正面"|"负面"|"中性", "score": 0到1的数字}。'
                ),
            }
            messages = messages + (
                [{"role": "assistant", "content": raw}, followup] if raw is not None else [followup]
            )
    raise RuntimeError(
        f"文本 {text!r} 分类失败（已重试 {MAX_ATTEMPTS} 次），最后错误: {last_error}"
    )


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    for text in TEXTS:
        result = classify_one(api_key, text)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
