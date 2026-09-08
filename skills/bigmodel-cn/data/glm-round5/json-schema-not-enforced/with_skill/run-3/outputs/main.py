#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对文本做情感分类，输出严格符合入库约束的 JSON。

用法：
    export ZHIPUAI_API_KEY=...
    python3 main.py

每条文本向 stdout 输出一行 JSON（可直接管道入库）：
    {"sentiment": "正面"|"负面"|"中性", "score": 0~1 之间的数字}

重要背景（官方文档 docs.bigmodel.cn/cn/guide/capabilities/struct-output）：
智谱 chat/completions 的 response_format 只支持 {"type": "json_object"}，
不支持 json_schema / strict 强约束——目标结构只能靠 prompt 描述，且输出
不保证 100% 合法（可能夹带解释文字、字段取值跑偏）。因此本脚本在客户端
做了三层兜底：字段级校验、把校验错误回喂模型重试、重试耗尽就报错退出
（宁可失败，也不往库里写脏数据）。
"""

import json
import math
import os
import sys
import time
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"           # 纯文本旗舰模型，支持 response_format
REASONING_EFFORT = "low"    # glm-5.3 在标准端点强制思考且不可关闭；分类是轻量任务，用 low 档（接近不思考）换低时延
REQUEST_TIMEOUT = 60        # 单次 HTTP 超时（秒）
MAX_REPAIR_ROUNDS = 3       # 输出不合法时，把错误回喂模型自纠的最大轮数
HTTP_BACKOFF = (1, 2, 4)    # 429/5xx/网络错误的指数退避间隔（秒）

VALID_SENTIMENTS = ("正面", "负面", "中性")

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是文本情感分类接口。对用户给出的文本做情感分类，只输出一个 JSON 对象，"
    "禁止输出任何其他内容（不要解释、不要 markdown 代码块、不要多余标点或换行）。\n\n"
    "输出格式（恰好两个字段，缺一不可、多一不可）：\n"
    '{"sentiment": "正面 或 负面 或 中性", "score": 0.9}\n\n'
    "字段约束（结果直接入库，违反任意一条即为脏数据）：\n"
    '- sentiment：字符串，只能恰好是 "正面"、"负面"、"中性" 三者之一，'
    "不能是英文、不能带空格或标点。\n"
    "- score：数字（不带引号、不带百分号），表示该分类的置信度，"
    "取值范围 [0, 1]，保留 1~2 位小数。"
)


def _extract_json_object(content: str) -> dict:
    """从模型返回的文本里解析出 JSON 对象。

    json_object 模式下通常直接就是合法 JSON；但官方文档明确说输出不保证
    合法，极端情况可能夹带解释文字或 markdown 围栏，这里逐层兜底。
    """
    text = content.strip()
    if text.startswith("```"):  # 剥掉 ```json ... ``` 围栏
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("输出中找不到 JSON 对象")
        obj = json.loads(text[start : end + 1])  # 解析失败会抛 ValueError，交给上层重试
    if not isinstance(obj, dict):
        raise ValueError("输出的 JSON 顶层不是对象")
    return obj


def _validate(obj: dict) -> dict:
    """字段级校验，返回归一化后的 {"sentiment": ..., "score": ...}。"""
    if set(obj) != {"sentiment", "score"}:
        raise ValueError(f"字段名不对：期望恰好 sentiment/score 两个字段，实际是 {sorted(obj)}")

    sentiment = obj["sentiment"]
    if not isinstance(sentiment, str) or sentiment.strip() not in VALID_SENTIMENTS:
        raise ValueError(f"sentiment 取值非法：{sentiment!r}，只能是 正面/负面/中性")

    raw_score = obj["score"]
    if isinstance(raw_score, bool):  # bool 是 int 的子类，必须先排除
        raise ValueError("score 不能是布尔值")
    if isinstance(raw_score, str):  # "0.9" 这类带引号的数字，宽容转换一次
        raw_score = raw_score.strip()
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        raise ValueError(f"score 不是数字：{obj['score']!r}")
    if not math.isfinite(score):
        raise ValueError(f"score 不是有限数字：{obj['score']!r}")
    if not 0.0 <= score <= 1.0:
        # 轻微越界（如 1.05）夹回 [0, 1]，保证入库不炸约束
        score = min(1.0, max(0.0, score))

    return {"sentiment": sentiment.strip(), "score": score}


def _post_chat(api_key: str, messages: list) -> str:
    """调用一次 chat/completions，返回模型文本。

    429（限流/平台过载）、5xx、网络错误按指数退避重试；
    400/401/403 等配置类错误重试无意义，直接抛出并带上业务错误码。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        # 平台不支持 json_schema（会被静默忽略），json_object 已是强约束上限，
        # 结构靠 SYSTEM_PROMPT 描述 + 客户端校验兜底
        "response_format": {"type": "json_object"},
        "reasoning_effort": REASONING_EFFORT,
        "temperature": 0.1,   # 分类任务要稳定，压低随机性
        "max_tokens": 1024,   # 输出只有一个 JSON 对象，1024 足够且留有余量
        "request_id": str(uuid.uuid4()),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = None
    last_err = None
    for backoff in (0,) + HTTP_BACKOFF:
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            last_err = e
            continue
        if resp.status_code < 400:
            break
        try:  # 带上响应体里的业务错误码（如 1113/1210/1302），方便排查
            err = resp.json().get("error", {})
            detail = f"{err.get('code')} {err.get('message')}"
        except ValueError:
            detail = resp.text[:200]
        last_err = RuntimeError(f"HTTP {resp.status_code}: {detail}")
        if resp.status_code == 429 or resp.status_code >= 500:
            continue  # 限流/服务端错误，退避后重试
        raise last_err  # 配置或参数问题，快速失败
    else:
        raise RuntimeError(f"请求重试后仍失败：{last_err}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应里没有 choices：{json.dumps(data, ensure_ascii=False)[:300]}")
    finish_reason = choices[0].get("finish_reason")
    if finish_reason != "stop":
        raise RuntimeError(f"finish_reason={finish_reason!r}，输出可能被截断或内容安全拦截")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("message.content 为空")
    return content


def classify(text: str, api_key: str) -> dict:
    """对单条文本分类；输出不合法时把错误回喂模型，最多自纠 MAX_REPAIR_ROUNDS 轮。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    last_err = None
    for _ in range(MAX_REPAIR_ROUNDS):
        content = _post_chat(api_key, messages)
        try:
            return _validate(_extract_json_object(content))
        except ValueError as e:
            last_err = e
            print(f"    输出不合法，回喂自纠：{e}", file=sys.stderr)
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"你上面的输出不合法：{e}。请重新只输出一个 JSON 对象，"
                        '格式为 {"sentiment": "正面"|"负面"|"中性", "score": 0~1 之间的数字}，'
                        "不要包含任何其他字符。"
                    ),
                },
            ]
    raise RuntimeError(f"自纠 {MAX_REPAIR_ROUNDS} 轮仍不合法，放弃以免写入脏数据（最后一次原因：{last_err}）")


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    for i, text in enumerate(TEXTS, 1):
        print(f"[{i}/{len(TEXTS)}] {text}", file=sys.stderr)
        try:
            result = classify(text, api_key)
        except RuntimeError as e:
            print(f"错误：{e}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
