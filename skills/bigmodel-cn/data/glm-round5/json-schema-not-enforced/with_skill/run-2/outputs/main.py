#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类，结果直接入库。

用法：
    ZHIPUAI_API_KEY=你的Key python3 main.py

stdout 每行输出一个 JSON 对象（JSONL，顺序与 TEXTS 一致），严格符合：
    {"sentiment": "正面" | "负面" | "中性", "score": 0到1之间的数字}

为什么不能只靠 API 保证格式：
    智谱 chat/completions 不支持 response_format.type="json_schema"（传了会被
    静默忽略），只支持 {"type": "json_object"}，且官方文档明确说明输出不保证
    100% 合法。所以本脚本用三层保障：
      1) json_object 模式 + system prompt 里写死目标结构；
      2) 客户端解析后做归一化与校验（sentiment 只认三个规范值，score 夹回 [0,1]）；
      3) 校验失败自动重试，重试耗尽宁可报错退出，也不输出不合规记录。
    最终写出的 dict 由代码显式构造（只含 sentiment/score 两个字段），
    不透传模型返回，杜绝多字段/错字段入库。
"""

import json
import math
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 纯文本旗舰模型，支持 response_format
TIMEOUT = 60            # 单次 HTTP 请求超时（秒）
MAX_HTTP_RETRIES = 3    # 网络/限流/5xx 的退避重试次数
MAX_PARSE_ATTEMPTS = 3  # 输出解析或校验失败时的整体重试次数（每次重新请求）

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

ALLOWED_SENTIMENTS = ("正面", "负面", "中性")

# 模型偶发输出同义词/英文/带空白的写法，先归一化成三个规范值；
# 归一化不了（比如乱编一个词）就视为本次尝试失败，走重试。
SENTIMENT_ALIASES = {
    "正面": "正面", "积极": "正面", "肯定": "正面", "好评": "正面",
    "positive": "正面", "pos": "正面",
    "负面": "负面", "消极": "负面", "否定": "负面", "差评": "负面",
    "negative": "负面", "neg": "负面",
    "中性": "中性", "中立": "中性", "neutral": "中性", "neu": "中性",
}

SYSTEM_PROMPT = (
    "你是一个情感分类接口，对用户给出的文本判断情感倾向。"
    "只输出一个 JSON 对象，结构严格为："
    '{"sentiment": "正面" 或 "负面" 或 "中性", "score": 0到1之间的小数}。'
    "要求："
    "1) sentiment 的取值只能是 正面、负面、中性 这三个中文词之一，"
    "禁止输出英文或其他同义词；"
    "2) score 是该分类的置信度，取 0 到 1 之间的数字（如 0.87），不要加百分号；"
    "3) 只输出这个 JSON 对象本身，不要输出任何解释、前后缀文字或 markdown 代码块。"
)


def log(msg):
    """日志走 stderr，保证 stdout 只有可入库的数据。"""
    print(msg, file=sys.stderr, flush=True)


def extract_json_block(text):
    """从模型返回文本中截出 JSON 对象片段。

    即使开了 json_object，极端情况下也可能夹带 ```json 代码块或说明文字，
    取第一个 '{' 到最后一个 '}' 之间的片段再解析。
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("返回内容里找不到 JSON 对象")
    return text[start:end + 1]


def parse_and_validate(content):
    """解析并校验模型输出，返回规范化的 {"sentiment", "score"}。

    校验失败抛 ValueError，由上层重试。
    """
    data = json.loads(extract_json_block(content))
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层不是对象")

    raw_sentiment = data.get("sentiment")
    if not isinstance(raw_sentiment, str):
        raise ValueError("缺少 sentiment 字段或不是字符串")
    sentiment = SENTIMENT_ALIASES.get(raw_sentiment.strip())
    if sentiment not in ALLOWED_SENTIMENTS:
        raise ValueError(f"sentiment 取值非法: {raw_sentiment!r}")

    raw_score = data.get("score")
    if isinstance(raw_score, bool):  # bool 是 int 的子类，先挡掉
        raise ValueError("score 不能是布尔值")
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        raise ValueError(f"score 不是数字: {raw_score!r}")
    if not math.isfinite(score):
        raise ValueError(f"score 不是有限数字: {raw_score!r}")
    score = min(1.0, max(0.0, score))  # 轻微越界夹回 [0,1]

    # 显式构造返回值：只有这两个字段，取值必然合规
    return {"sentiment": sentiment, "score": score}


def _api_error(resp):
    """提取智谱错误体 {"error": {"code": ..., "message": ...}}。"""
    try:
        err = resp.json().get("error") or {}
        return f"code={err.get('code')} message={err.get('message')}"
    except ValueError:
        return resp.text[:200]


def call_model(text, api_key):
    """调用 chat/completions 并返回 message.content。

    网络异常、HTTP 429/5xx 做指数退避重试；
    401/403/400 等配置或参数错误重试无意义，直接抛错。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        # 平台只支持 json_object；json_schema 会被静默忽略，不要传
        "response_format": {"type": "json_object"},
        # glm-5.3 在标准端点思考无法关闭，分类是轻量任务，用 low 档降低耗时
        "reasoning_effort": "low",
        "temperature": 0.1,  # 越低越稳定，利于格式与判断一致
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_err = exc  # 超时/连接抖动，可重试
        else:
            if resp.status_code >= 400:
                detail = _api_error(resp)
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = RuntimeError(f"HTTP {resp.status_code}: {detail}")
                else:
                    raise RuntimeError(
                        f"API 调用失败（配置或参数问题，不重试）HTTP {resp.status_code}: {detail}"
                    )
            else:
                choices = resp.json().get("choices") or []
                if not choices:
                    last_err = RuntimeError(f"响应里没有 choices: {resp.json()}")
                else:
                    finish_reason = choices[0].get("finish_reason")
                    content = (choices[0].get("message") or {}).get("content")
                    # sensitive/network_error/length 等异常结束拿不到可靠输出
                    if finish_reason != "stop" or not isinstance(content, str) or not content.strip():
                        last_err = RuntimeError(f"异常结束 finish_reason={finish_reason!r}")
                    else:
                        return content
        if attempt < MAX_HTTP_RETRIES:
            time.sleep(2 ** attempt)  # 指数退避：2s、4s，避免加重限流
    raise RuntimeError(f"API 重试 {MAX_HTTP_RETRIES} 次仍失败: {last_err}")


def classify(text, api_key):
    """对单条文本做情感分类，输出/校验失败时自动重试。"""
    for attempt in range(1, MAX_PARSE_ATTEMPTS + 1):
        try:
            return parse_and_validate(call_model(text, api_key))
        except (ValueError, KeyError, TypeError) as exc:  # JSONDecodeError 是 ValueError 子类
            log(f"[重试 {attempt}/{MAX_PARSE_ATTEMPTS}] 输出不合法（{exc}）: {text}")
            if attempt == MAX_PARSE_ATTEMPTS:
                raise RuntimeError(
                    f"文本 {text!r} 连续 {MAX_PARSE_ATTEMPTS} 次未得到合规结果，"
                    "已中止——宁可不入库，也不写脏数据"
                ) from exc
            time.sleep(1)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        log("错误：请先设置环境变量 ZHIPUAI_API_KEY（https://bigmodel.cn/usercenter/proj-mgmt/apikeys）")
        return 1

    for text in TEXTS:
        result = classify(text, api_key)
        # stdout 只输出严格符合约定的 JSON，一行一条，可直接管道入库
        print(json.dumps(result, ensure_ascii=False), flush=True)
        log(f"完成: {text} -> {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
