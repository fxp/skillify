#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类。

输出（stdout，JSON 数组，顺序与输入一致）中每个元素严格符合：
    {"sentiment": "正面" | "负面" | "中性", "score": 0 到 1 之间的数字}

注意：智谱平台的 response_format 只支持 text/json_object，不存在
json_schema/strict 强约束模式（传了会被静默忽略），因此这里用
json_object + system prompt 描述结构，并在客户端做严格校验与
失败重试兜底，保证绝不输出脏数据。

用法：
    ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import re
import sys
import time
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
VALID_SENTIMENTS = ("正面", "负面", "中性")
MAX_ATTEMPTS = 3            # 单条文本：调用 + 解析 + 校验 的总尝试次数
RETRY_BACKOFF_SECONDS = 1   # 指数退避基数：1s, 2s, ...
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}  # 限流/过载/服务端错误才值得重试
REQUEST_TIMEOUT = 60

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是一个情感分类接口。对用户发送的一条文本做情感分类，"
    "只输出一个 JSON 对象，禁止输出任何解释、注释、markdown 代码块或其他多余字符。\n"
    "JSON 必须恰好包含以下两个字段，字段名和取值都不能变：\n"
    '- "sentiment"：字符串，只能取 "正面"、"负面"、"中性" 三者之一\n'
    '- "score"：数字，表示该分类的置信度，取值范围 0 到 1（含边界）\n'
    '示例输出：{"sentiment": "正面", "score": 0.93}'
)


class ApiCallError(Exception):
    """API 调用或输出格式问题，重试可能解决。"""


class ConfigError(Exception):
    """配置/参数类错误（401/403/400 等），重试没有意义。"""


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise ConfigError("环境变量 ZHIPUAI_API_KEY 未设置，请先 export ZHIPUAI_API_KEY=<你的Key>")
    return key


def call_chat_api(api_key, text):
    """调用一次 chat/completions，返回 message.content 字符串。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},  # 平台无 json_schema 强约束
        "do_sample": False,          # 贪心解码：分类任务要确定性，temperature/top_p 被忽略
        "reasoning_effort": "low",   # glm-5.3 标准端点强制思考且不能 disabled（报 1210），轻量分类用 low
        "max_tokens": 2048,
        "request_id": str(uuid.uuid4()),
    }
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise ApiCallError(f"网络请求失败：{exc}") from exc

    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
            detail = f"业务码 {err.get('code', '?')}：{err.get('message', '')}"
        except ValueError:
            detail = resp.text[:200]
        if resp.status_code in RETRYABLE_HTTP_STATUS:
            raise ApiCallError(f"HTTP {resp.status_code}（{detail}）")
        raise ConfigError(f"HTTP {resp.status_code}（{detail}），请检查 API Key / 参数")

    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiCallError(f"响应不是合法 JSON：{resp.text[:200]}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise ApiCallError(f"响应缺少 choices：{json.dumps(data, ensure_ascii=False)[:200]}")
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason != "stop":
        # sensitive / length / network_error 等都视为失败，不能拿去入库
        raise ApiCallError(f"finish_reason={finish_reason!r}，非正常结束")
    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ApiCallError("message.content 为空")
    return content


def extract_json_object(content):
    """从模型回复中提取 JSON 对象；整体 loads 失败则截取最外层 {...} 再试。"""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"无法从回复中提取 JSON：{content[:100]!r}")


def validate_result(obj):
    """严格校验并归一化；不合法抛 ValueError（触发重试）。"""
    if not isinstance(obj, dict):
        raise ValueError(f"结果不是 JSON 对象：{obj!r}")
    if set(obj) != {"sentiment", "score"}:
        raise ValueError(f"字段必须恰好为 sentiment/score，实际：{sorted(obj)}")
    sentiment = obj["sentiment"]
    if sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"sentiment 必须是 正面/负面/中性 之一，实际：{sentiment!r}")
    score = obj["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(f"score 必须是数字，实际：{score!r}")
    # score 语义是置信度，轻微越界安全夹紧到 [0, 1]，保证入库值合法
    return {"sentiment": sentiment, "score": min(1.0, max(0.0, float(score)))}


def classify_text(api_key, text):
    """对单条文本分类，返回 {"sentiment": ..., "score": ...}；重试耗尽抛 RuntimeError。"""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 2)))
        try:
            content = call_chat_api(api_key, text)
            return validate_result(extract_json_object(content))
        except ConfigError:
            raise
        except (ApiCallError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(f"文本 {text!r} 分类失败（已尝试 {MAX_ATTEMPTS} 次）：{last_error}")


def main():
    api_key = get_api_key()
    # 串行调用：平台限流按并发数计算，3 条文本无需并发
    results = [classify_text(api_key, text) for text in TEXTS]
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ConfigError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
