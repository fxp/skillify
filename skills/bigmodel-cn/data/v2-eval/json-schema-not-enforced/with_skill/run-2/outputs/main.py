#!/usr/bin/env python3
"""用智谱 GLM 对文本做情感分类，输出严格结构的 JSONL（每行一个 JSON 对象）。

结果直接入下游数据库，字段和取值有硬约束：
    {"sentiment": "正面" | "负面" | "中性", "score": 0 到 1 之间的数字}

实现要点（来自 bigmodel.cn 接入实测，不能省）：
1. 平台 response_format 只有 text/json_object 两种取值，没有 json_schema 严格模式，
   传了也会被静默忽略——所以字段结构在 system prompt 里写死，且客户端做严格的
   二次校验 + 失败重试，任何一次校验不过就重试，重试耗尽直接报错退出，
   绝不把未通过校验的结果打印出去（宁失败，不出脏数据）。
2. glm-5.3 在标准端点强制开启思考，且思考 token 计入 max_tokens 预算——预算给足
   （2048），并把 finish_reason=length 当作失败重试，避免拿到被截断的半截 JSON。
"""

import json
import os
import re
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
MAX_ATTEMPTS = 3  # 每条文本的最多尝试次数（解析/校验失败、截断、网络抖动都重试）
REQUEST_TIMEOUT = 60  # 秒

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是一个情感分类引擎，负责判断用户提交文本的情感倾向。\n"
    "你只能输出一个 JSON 对象，有且仅有下面两个字段，不得增删：\n"
    '{"sentiment": "正面", "score": 0.95}\n'
    "字段规则：\n"
    '- sentiment 的取值只能是 "正面"、"负面"、"中性" 三者之一，'
    "分别对应褒义、贬义、无明显倾向，禁止输出其他任何值；\n"
    "- score 是该情感判断的置信度，必须是 0 到 1 之间的数字，保留两位小数；\n"
    "- 只输出这个 JSON 对象本身，不要输出解释、Markdown 代码块或任何多余内容。"
)


def classify(text: str, api_key: str) -> dict:
    """对单条文本做情感分类，返回通过严格校验的 {"sentiment": ..., "score": ...}。

    解析失败、字段校验不过、输出被截断、网络/接口错误都视为一次失败并重试；
    MAX_ATTEMPTS 次仍失败则抛 RuntimeError（让调用方失败退出，而不是产出脏数据）。
    """
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = _call_api(text, api_key)
            record = _extract_json(raw)
            _validate(record)
            return record
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = "第 {} 次尝试失败: {}".format(attempt, exc)
    raise RuntimeError(
        "文本 {!r} 经 {} 次尝试仍未得到符合结构的输出，中止以免写入脏数据；"
        "最后一次错误：{}".format(text, MAX_ATTEMPTS, last_error)
    )


def _call_api(text: str, api_key: str) -> str:
    """调用同步对话补全接口，返回 message.content 字符串。"""
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "待分类文本：\n" + text},
            ],
            # 平台没有 json_schema 严格模式，json_object 只保证"是合法 JSON"，
            # 字段结构靠上面的 system prompt 约束 + 下面的 _validate 兜底。
            "response_format": {"type": "json_object"},
            "reasoning_effort": "low",  # 分类任务不需要深思考，省思考 token（glm-5.3 接受 low/high/max）
            "max_tokens": 2048,  # 思考 token 计入预算，给足以免内容被截断
            "do_sample": False,  # 贪心解码，分类结果更稳定
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError("接口返回 HTTP {}: {}".format(resp.status_code, resp.text[:500]))
    body = resp.json()
    choice = body["choices"][0]
    finish_reason = choice.get("finish_reason")
    content = choice["message"].get("content")
    if finish_reason == "length":
        # 预算被思考 token 吃光或输出被截断，content 可能是空串或半截 JSON
        raise RuntimeError("finish_reason=length，输出被截断")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("接口返回空内容（finish_reason={}）".format(finish_reason))
    return content.strip()


def _extract_json(raw: str) -> dict:
    """从模型输出中解析出 JSON 对象。

    json_object 模式下通常整段就是 JSON；极端情况可能夹带解释文字或 Markdown
    代码块（实测踩坑），所以 json.loads 直解失败后再做一次花括号配对截取。
    """
    stripped = raw.strip()
    if stripped.startswith("```"):  # 剥掉 Markdown 代码块围栏
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # 兜底：找第一个配平的 {...} 块（跳过字符串里的花括号）
    start = stripped.find("{")
    if start == -1:
        raise ValueError("输出中不含 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(stripped[start:], start=start):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(stripped[start : i + 1])
    raise ValueError("未找到配平的 JSON 对象")


def _validate(record) -> None:
    """严格校验结果结构，不符合则抛 ValueError（触发重试）。

    校验规则与下游数据库约束一一对应：字段名不多不少、sentiment 三选一、
    score 是 0 到 1 之间的数字（bool 不算数字）。
    """
    if not isinstance(record, dict):
        raise ValueError("期望 JSON 对象，实际是 {}".format(type(record).__name__))
    if set(record.keys()) != {"sentiment", "score"}:
        raise ValueError("字段名不符: {}".format(sorted(record.keys())))
    if record["sentiment"] not in VALID_SENTIMENTS:
        raise ValueError("sentiment 取值非法: {!r}".format(record["sentiment"]))
    score = record["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("score 不是数字: {!r}".format(score))
    if not 0 <= score <= 1:
        raise ValueError("score 超出 [0, 1]: {!r}".format(score))


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用接口。"
            "请先执行：export ZHIPUAI_API_KEY=你的APIKey",
            file=sys.stderr,
        )
        return 1
    for text in TEXTS:  # 顺序调用：平台速率限制按并发算，不做并发
        record = classify(text, api_key)
        # 每行一个严格结构的 JSON 对象（JSONL），可直接入库
        print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
