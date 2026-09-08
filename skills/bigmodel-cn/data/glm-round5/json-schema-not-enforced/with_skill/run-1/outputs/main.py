#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感三分类，输出严格符合下游入库约束的记录：

    {"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的数字}

接入要点（依据 bigmodel-cn 接入手册 + 官方文档核实）：
- 端点 POST https://open.bigmodel.cn/api/paas/v4/chat/completions，Bearer 鉴权，
  Key 从环境变量 ZHIPUAI_API_KEY 读取。
- 智谱不支持 response_format.type = "json_schema"（传了会被静默忽略），
  只有 "json_object"。因此字段结构只能写进 prompt 约束，且客户端必须自己做
  json.loads + 字段校验 + 失败重试，不能假设模型输出 100% 合法——这是本脚本的重点。
- glm-5.3 在标准端点强制思考、无法用 thinking.type=disabled 关闭（报 1210），
  分类这类轻量任务用 reasoning_effort="low" 代替；do_sample=False 走贪心解码，
  输出更稳定（也因此重试时必须追加纠错上下文，否则同样的 prompt 会得到同样的输出）。
- 速率限制按并发计算：3 条文本串行请求，不并发。
- 任何一条文本重试后仍不合规就报错退出（exit 1），不输出兜底记录，防止脏数据入库。
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

ALLOWED_SENTIMENTS = ("正面", "负面", "中性")
# 模型偶尔会输出英文标签，映射回中文再入库（映射是定义等价的，不会造成脏数据）
SENTIMENT_ALIASES = {"positive": "正面", "negative": "负面", "neutral": "中性"}

MAX_PARSE_RETRIES = 3  # 单条文本输出不合规时的最大尝试次数
MAX_HTTP_RETRIES = 3   # 网络/限流/服务端错误的退避重试次数

SYSTEM_PROMPT = (
    "你是情感分类引擎。对用户给出的文本做情感三分类，只输出一个 JSON 对象，"
    "禁止输出任何其他内容（包括解释、前后缀文字、markdown 代码块标记）。\n"
    "JSON 结构固定为且仅有两个字段：\n"
    '{"sentiment": "正面"、"负面"或"中性", "score": 0到1之间的数字}\n'
    "规则：\n"
    '1. sentiment 只能取 "正面"、"负面"、"中性" 三个中文字符串之一；\n'
    "2. score 是你对这个分类的置信度，必须是数字（不能是字符串），取值范围 [0, 1]；\n"
    "3. 只允许 sentiment 和 score 这两个字段，字段名一字不差，不要嵌套、不要增删字段。"
)


def log(msg: str) -> None:
    """过程日志走 stderr，保证 stdout 只有可入库的 JSON 行。"""
    print(msg, file=sys.stderr)


def extract_json_object(raw: str) -> object:
    """从模型输出中提取 JSON。

    json_object 模式不是强约束，模型可能夹带 ```json 围栏或解释文字，
    所以依次尝试：原文直接解析 -> 剥掉围栏 -> 截取首尾大括号之间的内容。
    """
    text = raw.strip()
    candidates = [text]
    if "```" in text:
        candidates.append(
            text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
        )
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    raise ValueError(f"无法解析为 JSON: {raw!r}")


def validate_result(data: object) -> dict:
    """严格校验并归一化模型输出，不合规抛 ValueError（由上层触发纠错重试）。"""
    if not isinstance(data, dict):
        raise ValueError("输出不是 JSON 对象")
    if set(data.keys()) != {"sentiment", "score"}:
        raise ValueError(f"字段名不符合约定: {sorted(data.keys())}")

    sentiment = data["sentiment"]
    if isinstance(sentiment, str):
        stripped = sentiment.strip()
        if stripped in ALLOWED_SENTIMENTS:
            sentiment = stripped
        else:
            sentiment = SENTIMENT_ALIASES.get(stripped.lower())
    if sentiment not in ALLOWED_SENTIMENTS:
        raise ValueError(f"sentiment 取值非法: {data['sentiment']!r}")

    score = data["score"]
    if isinstance(score, bool):  # bool 是 int 的子类，先排除
        raise ValueError(f"score 取值非法: {score!r}")
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError:
            raise ValueError(f"score 不是数字: {score!r}") from None
    if not isinstance(score, (int, float)):
        raise ValueError(f"score 不是数字: {score!r}")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score 超出 [0,1]: {score!r}")

    return {"sentiment": sentiment, "score": round(float(score), 2)}


def chat(messages: list, api_key: str) -> str:
    """调用一次对话补全，返回 message.content。网络/限流错误退避重试。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "reasoning_effort": "low",   # glm-5.3 标准端点无法关闭思考，用 low 档做轻量分类
        "do_sample": False,          # 贪心解码，输出稳定
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(MAX_HTTP_RETRIES):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_err = exc
            log(f"[网络错误] 第 {attempt + 1}/{MAX_HTTP_RETRIES} 次: {exc}")
        else:
            # 4xx（除 429 限流）是鉴权/参数问题，重试无意义，直接报错
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {resp.text}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    raise RuntimeError(f"API 响应不是 JSON: {resp.text!r}") from None
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"API 响应缺少 choices: {data}")
                finish_reason = choices[0].get("finish_reason")
                if finish_reason != "stop":
                    # sensitive / network_error / length 等都视为本次输出不可信
                    raise RuntimeError(f"finish_reason={finish_reason!r}，本次输出不可用")
                content = choices[0]["message"].get("content")
                if not content:
                    raise RuntimeError("模型 content 为空")
                return content
            last_err = RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {resp.text}")
            log(f"[服务端错误] 第 {attempt + 1}/{MAX_HTTP_RETRIES} 次: {last_err}")
        if attempt < MAX_HTTP_RETRIES - 1:
            time.sleep(0.5 * (2 ** attempt))  # 指数退避，避免加重限流
    raise RuntimeError(f"请求重试 {MAX_HTTP_RETRIES} 次仍失败: {last_err}")


def classify(text: str, api_key: str) -> dict:
    """对单条文本做情感分类，返回校验通过的 {"sentiment", "score"}。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    last_err = None
    for attempt in range(1, MAX_PARSE_RETRIES + 1):
        raw = chat(messages, api_key)
        try:
            return validate_result(extract_json_object(raw))
        except ValueError as exc:
            last_err = exc
            log(f"[输出不合规] {text!r} 第 {attempt}/{MAX_PARSE_RETRIES} 次: {exc}")
            # do_sample=False 下原样重发会得到同样输出，
            # 必须把错误输出带回并追加纠错指令，重试才有意义
            messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"你上一次的输出不符合要求：{exc}。请重新输出，"
                        '只输出一个 JSON 对象：{"sentiment": "正面"|"负面"|"中性", '
                        '"score": 0到1之间的数字}，不要有任何其他文字。'
                    ),
                },
            ]
    raise RuntimeError(
        f"文本 {text!r} 经过 {MAX_PARSE_RETRIES} 次尝试仍未得到合规输出: {last_err}"
    )


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        log("错误：请先设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    for text in TEXTS:
        result = classify(text, api_key)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
