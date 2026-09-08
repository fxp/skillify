#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类。

对 TEXTS 中的每条文本调用智谱对话补全接口，输出严格符合
    {"sentiment": "正面" | "负面" | "中性", "score": 0 到 1 之间的数字}
的结果：每条输入对应一行 JSON（JSON Lines，顺序与 TEXTS 一致），可直接入库。

用法：
    export ZHIPUAI_API_KEY=你的key
    python3 main.py

说明：
- 第三方依赖只有 requests，其余均为标准库。
- 接口的 JSON 模式并不保证字段和取值完全符合约定，所以脚本内做了强校验：
  解析失败、字段缺失、sentiment 不在三枚举值内、score 不是 [0,1] 内的数字，
  都会触发重试；重试耗尽仍失败则整体报错退出，不输出任何一行，避免脏数据入库。
"""

import json
import math
import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 文档示例中的旗舰模型；glm-5.3 系列只能开启思维链，故不传 thinking 参数，
# 推理内容在 reasoning_content 字段里，不影响最终 JSON 在 content 中。
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")
REQUEST_TIMEOUT = 60        # 单次请求超时（秒）
MAX_ATTEMPTS = 3            # 每条文本的最大尝试次数
RETRY_BACKOFF_SECONDS = 1.0  # 重试退避基数（第 n 次失败后睡 n * 基数秒）

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是文本情感分类器。只输出一个 JSON 对象，"
    "不要输出任何解释性文字或 Markdown 代码块。\n"
    "JSON 必须且只能包含两个字段：\n"
    '- "sentiment"：字符串，只能取 "正面"、"负面"、"中性" 三者之一；\n'
    '- "score"：数字，表示该分类的置信度，取值范围 [0, 1]。\n'
    '输出示例：{"sentiment": "正面", "score": 0.92}'
)


class ApiCallError(RuntimeError):
    """不可重试的接口错误（鉴权失败、请求参数非法等）。"""


def build_payload(text):
    """构造单次对话补全请求体。"""
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "待分类文本：" + text},
        ],
        "temperature": 0.1,  # 分类任务，尽量压低随机性
        "response_format": {"type": "json_object"},  # 开启 JSON 输出模式
    }


def extract_json_object(raw):
    """从模型返回的文本里提取 JSON 对象，返回 dict；失败返回 None。

    正常情况（json_object 模式）raw 就是纯 JSON；这里额外兜底处理
    代码块围栏和前后多余文字，避免因为格式小毛病浪费一次重试。
    """
    if not raw:
        return None
    text = raw.strip()

    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def coerce_score(value):
    """把 score 规整为 [0,1] 内的 float；不合法返回 None。

    容忍模型把数字写成字符串（"0.9"），但排除 bool（bool 是 int 的子类）、
    nan/inf 以及超出 [0,1] 的值。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    if number < 0.0 or number > 1.0:
        return None
    return number


def validate_result(obj):
    """校验模型输出并组装成最终结构；不合法返回 None。

    sentiment 不做"积极 -> 正面"之类的同义词映射：枚举值错了就该重试，
    静默改写标签有把语义改错的风险。
    """
    if not isinstance(obj, dict):
        return None
    if "sentiment" not in obj or "score" not in obj:
        return None
    sentiment = obj["sentiment"]
    if not isinstance(sentiment, str):
        return None
    sentiment = sentiment.strip()  # 只去首尾空白，不会改变三个标签的语义
    if sentiment not in VALID_SENTIMENTS:
        return None
    score = coerce_score(obj["score"])
    if score is None:
        return None
    # 重新组装，只保留约定的两个字段；模型多吐的字段一律丢弃
    return {"sentiment": sentiment, "score": score}


def classify_sentiment(text, api_key):
    """对单条文本做情感分类，返回 {"sentiment": ..., "score": ...}。

    结构不合法或遇到临时性网络/服务端错误时重试；鉴权等不可重试错误
    直接抛 ApiCallError。
    """
    last_reason = "未知错误"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                API_URL,
                json=build_payload(text),
                headers={"Authorization": "Bearer " + api_key},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            last_reason = "网络错误：%s" % exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue

        if resp.status_code != 200:
            snippet = resp.text[:200]
            if resp.status_code == 429 or resp.status_code >= 500:
                # 限流 / 服务端临时故障，值得重试
                last_reason = "HTTP %d：%s" % (resp.status_code, snippet)
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            # 其余 4xx（鉴权失败、参数非法等）重试没有意义
            raise ApiCallError(
                "接口返回 HTTP %d（不可重试）：%s" % (resp.status_code, snippet)
            )

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            last_reason = "响应结构异常：%s" % resp.text[:200]
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue

        result = validate_result(extract_json_object(content))
        if result is not None:
            return result

        last_reason = "第 %d 次输出不符合约定结构：%r" % (attempt, content)
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise ApiCallError(
        "文本 %r 分类失败（已尝试 %d 次），最后原因：%s"
        % (text, MAX_ATTEMPTS, last_reason)
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY。", file=sys.stderr)
        return 2

    results = []
    try:
        for text in TEXTS:
            results.append(classify_sentiment(text, api_key))
    except ApiCallError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 1

    # 三条全部成功才统一输出，避免部分结果先入库形成脏数据
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
