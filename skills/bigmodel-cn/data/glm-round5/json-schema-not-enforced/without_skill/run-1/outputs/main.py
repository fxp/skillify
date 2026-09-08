# -*- coding: utf-8 -*-
"""用智谱 GLM 对一批中文评论做情感分类。

输出（stdout，每行一个 JSON 对象，行序与输入 TEXTS 一一对应）：
    {"sentiment": "正面", "score": 0.93}
    {"sentiment": "负面", "score": 0.97}
    {"sentiment": "中性", "score": 0.88}

约定：
- API Key 从环境变量 ZHIPUAI_API_KEY 读取；
- 结果直接入库，字段名和取值必须严格符合上述结构。GLM 的 json_object 模式
  只保证"是合法 JSON"，不校验具体字段，所以脚本在本地做严格校验：
  字段不齐/多字段/sentiment 不在三选一/score 不在 [0,1] 都视为失败并重试；
  重试耗尽则整体报错退出、不输出任何部分结果——宁可失败也不写脏数据。

用法：
    export ZHIPUAI_API_KEY="你的APIKey"
    python3 main.py
"""

import json
import math
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 默认用旗舰模型保证输出合规；账户里没有的话可用环境变量 GLM_MODEL 换成
# 其他文本模型（如 glm-4.7-flash），可用列表见 https://docs.bigmodel.cn
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")
TEMPERATURE = 0.1  # 分类任务要稳定，取低温
REQUEST_TIMEOUT = 60  # 单次请求超时（秒）
MAX_ATTEMPTS = 4  # 每条文本的最大尝试次数
RETRY_BACKOFF_SECONDS = 2  # 重试退避：第 n 次失败后等 n*2 秒

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")
VALID_KEYS = {"sentiment", "score"}

SYSTEM_PROMPT = (
    "你是一个情感分类接口。对用户给出的中文评论判断情感倾向，"
    "只输出一个 JSON 对象，不要输出任何解释、前后缀或 Markdown 代码块。\n"
    "JSON 格式（字段名与取值严格如下，不得增删字段、不得改写取值）：\n"
    '{"sentiment": "正面" | "负面" | "中性", "score": 0到1之间的数字}\n'
    "规则：\n"
    '1. sentiment 只能是 "正面"、"负面"、"中性" 三个字符串之一，原样输出，不要翻译或改写；\n'
    "2. score 是该分类的置信度，0 到 1 之间的数字（例如 0.87），不要加引号；\n"
    "3. 除这个 JSON 对象外，不要输出任何其他内容。"
)


class GLMError(RuntimeError):
    """GLM 调用失败或返回结果不符合约定结构。"""


def call_glm(api_key: str, text: str) -> str:
    """调用智谱 GLM 对话补全接口，返回模型输出的文本。

    网络/超时错误抛 requests.RequestException，HTTP 非 200 或内容异常抛 GLMError。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": TEMPERATURE,
        # GLM 的 JSON 输出模式：约束模型只产出合法 JSON（字段仍需本地校验）
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    response = requests.post(
        API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
    )
    if response.status_code != 200:
        raise GLMError(f"HTTP {response.status_code}: {response.text[:200]}")
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise GLMError(f"响应中没有 choices: {str(body)[:200]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GLMError(
            f"content 为空（finish_reason={choices[0].get('finish_reason')}）"
        )
    return content


def parse_result(content: str) -> dict:
    """把模型输出解析并校验成严格符合 {"sentiment", "score"} 的 dict。

    模型偶尔会带代码块围栏或前后缀，所以先截取第一个 "{" 到最后一个 "}"
    之间的内容再解析；任何不合规都抛 GLMError，由上层重试。
    """
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise GLMError(f"返回内容中找不到 JSON 对象: {text[:200]!r}")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GLMError(f"JSON 解析失败: {exc}；原文: {text[:200]!r}") from exc

    if not isinstance(data, dict):
        raise GLMError(f"JSON 顶层不是对象: {text[:200]!r}")
    if set(data) != VALID_KEYS:
        raise GLMError(
            f"字段不合规（需要且仅需要 {sorted(VALID_KEYS)}）: {data!r}"
        )

    sentiment = data["sentiment"]
    if sentiment not in VALID_SENTIMENTS:
        raise GLMError(f"sentiment 取值非法（只能是 正面/负面/中性）: {sentiment!r}")

    # score 必须能当数字用（容忍模型给出字符串数字），并收敛到 [0,1]、
    # 保留 4 位小数，避免浮点尾巴入库；bool 是 int 子类，先排除
    score = data["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float, str)):
        raise GLMError(f"score 不是数字: {score!r}")
    try:
        score = float(score)
    except ValueError as exc:
        raise GLMError(f"score 无法转成数字: {score!r}") from exc
    if not math.isfinite(score):
        raise GLMError(f"score 不是有限数字: {data['score']!r}")
    score = round(min(max(score, 0.0), 1.0), 4)

    return {"sentiment": sentiment, "score": score}


def classify_one(api_key: str, text: str) -> dict:
    """对单条文本做情感分类，失败自动重试；重试耗尽抛 GLMError。"""
    last_error: Exception = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return parse_result(call_glm(api_key, text))
        except (requests.RequestException, GLMError, ValueError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                delay = RETRY_BACKOFF_SECONDS * attempt
                print(
                    f"[重试] 第 {attempt}/{MAX_ATTEMPTS} 次尝试失败（{text}）："
                    f"{exc}，{delay}s 后重试",
                    file=sys.stderr,
                )
                time.sleep(delay)
    raise GLMError(f"文本 {text!r} 重试 {MAX_ATTEMPTS} 次后仍失败：{last_error}")


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，请先 "
            "export ZHIPUAI_API_KEY=<你的APIKey>",
            file=sys.stderr,
        )
        return 1

    try:
        results = [classify_one(api_key, text) for text in TEXTS]
    except (GLMError, requests.RequestException) as exc:
        print(f"错误：情感分类失败，未输出任何结果：{exc}", file=sys.stderr)
        return 1

    # 全部成功才输出，保证行数与输入一一对应，不产生对不齐的半截数据
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
