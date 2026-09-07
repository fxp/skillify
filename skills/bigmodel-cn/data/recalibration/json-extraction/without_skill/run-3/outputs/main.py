#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱 GLM 模型
把每条反馈抽取成结构化信息，写出同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
    name        反馈人姓名
    issue_type  问题类型（由模型归类）
    urgency     紧急程度，只能是 low / medium / high

依赖：仅 requests（标准库之外）
用法：
    export ZHIPUAI_API_KEY=xxxxxxxx
    python3 main.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------- 配置 ----

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "feedback.txt"
OUTPUT_FILE = BASE_DIR / "out.json"

REQUEST_TIMEOUT = 120          # 单次请求超时（秒）
MAX_RETRIES = 3                # 单条反馈最多尝试次数
RETRY_BACKOFF = 2.0            # 重试退避基数（秒）

VALID_URGENCY = ("low", "medium", "high")

SYSTEM_PROMPT = """你是一个客户反馈信息抽取器。

用户会给你一条客户反馈文本，你必须只输出一个 JSON 对象，且该对象恰好包含以下三个键：

1. "name": 字符串。反馈人的姓名。如果反馈中没有出现姓名，填 "未知"。
2. "issue_type": 字符串。你对该反馈的问题类型归类，用简短的中文名词短语
   （例如 "物流延迟"、"产品质量"、"退款问题"、"客服态度"、"账号登录"、
   "功能建议"、"计费争议" 等）。同类问题请使用一致的措辞。
3. "urgency": 字符串。紧急程度，只能是 "low"、"medium"、"high" 三者之一。
   - high: 影响资金/安全/无法使用核心功能，或客户明确表达强烈不满、威胁投诉与退款。
   - medium: 明显影响体验但有变通办法，客户有抱怨但语气可控。
   - low: 一般性建议、轻微不便、称赞中夹带的小意见。

严格要求：
- 只输出 JSON 对象本身，不要输出解释、不要输出 Markdown 代码块标记。
- 不要增加任何额外的键，也不要遗漏任何键。
- urgency 的值必须是小写的 low / medium / high。"""


# ------------------------------------------------------------ 工具函数 ----

def die(msg: str) -> "None":
    print("错误: {}".format(msg), file=sys.stderr)
    sys.exit(1)


def get_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die("环境变量 ZHIPUAI_API_KEY 未设置。请先执行: export ZHIPUAI_API_KEY=你的密钥")
    return key


def read_feedback(path: Path):
    if not path.exists():
        die("找不到输入文件: {}".format(path))
    lines = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            text = raw.strip()
            if text:
                lines.append(text)
    if not lines:
        die("输入文件 {} 中没有有效的反馈内容。".format(path))
    return lines


def extract_json_object(text: str):
    """从模型输出中尽力提取出第一个 JSON 对象。"""
    if not text:
        return None

    cleaned = text.strip()

    # 去掉 ```json ... ``` 之类的围栏
    fence = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass

    # 退而求其次：扫描出第一个配平的 {...} 片段
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(cleaned):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except (ValueError, TypeError):
                        start = -1
    return None


def normalize_urgency(value) -> str:
    """把模型返回的紧急程度归一到 low / medium / high。"""
    text = str(value or "").strip().lower()
    if text in VALID_URGENCY:
        return text

    mapping = {
        "低": "low", "一般": "low", "轻微": "low", "not urgent": "low",
        "中": "medium", "中等": "medium", "普通": "medium", "moderate": "medium",
        "高": "high", "紧急": "high", "非常紧急": "high", "urgent": "high",
        "critical": "high", "严重": "high",
    }
    if text in mapping:
        return mapping[text]

    for level in ("high", "medium", "low"):
        if level in text:
            return level

    return "medium"  # 兜底，保证字段合法


def normalize_record(obj: dict, fallback_text: str) -> dict:
    """保证结果恰好是三个键，且取值类型正确。"""
    name = obj.get("name")
    name = str(name).strip() if name is not None else ""
    if not name:
        name = "未知"

    issue_type = obj.get("issue_type")
    issue_type = str(issue_type).strip() if issue_type is not None else ""
    if not issue_type:
        issue_type = "其他"

    return {
        "name": name,
        "issue_type": issue_type,
        "urgency": normalize_urgency(obj.get("urgency")),
    }


# --------------------------------------------------------------- 调用 ----

def call_model(session: requests.Session, api_key: str, feedback: str) -> dict:
    """调用智谱对话补全接口，返回抽取出的 JSON 对象。失败抛异常。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "客户反馈：\n{}".format(feedback)},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
        # GLM-4.5 及以上支持思考开关；抽取任务不需要思维链，关掉更快更稳
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }

    resp = session.post(
        API_URL,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            "HTTP {}: {}".format(resp.status_code, resp.text[:500])
        )

    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("响应中没有 choices: {}".format(str(body)[:500]))

    content = (choices[0].get("message") or {}).get("content") or ""
    obj = extract_json_object(content)
    if obj is None:
        raise RuntimeError("无法从模型输出中解析出 JSON: {}".format(content[:300]))
    return obj


def extract_one(session, api_key: str, feedback: str, index: int, total: int) -> dict:
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            obj = call_model(session, api_key, feedback)
            return normalize_record(obj, feedback)
        except Exception as exc:  # 网络/解析/限流等一律重试
            last_err = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(
                    "  [{}/{}] 第 {} 次尝试失败（{}），{:.0f}s 后重试...".format(
                        index, total, attempt, exc, wait
                    ),
                    file=sys.stderr,
                )
                time.sleep(wait)

    print(
        "  [{}/{}] 抽取失败，使用兜底值。最后一次错误: {}".format(index, total, last_err),
        file=sys.stderr,
    )
    return {"name": "未知", "issue_type": "抽取失败", "urgency": "medium"}


# --------------------------------------------------------------- 主流程 ----

def main() -> int:
    api_key = get_api_key()
    feedbacks = read_feedback(INPUT_FILE)
    total = len(feedbacks)
    print("读取到 {} 条反馈，使用模型 {} 开始抽取...".format(total, MODEL))

    results = []
    with requests.Session() as session:
        for i, feedback in enumerate(feedbacks, start=1):
            preview = feedback if len(feedback) <= 40 else feedback[:40] + "..."
            print("[{}/{}] {}".format(i, total, preview))
            results.append(extract_one(session, api_key, feedback, i, total))

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("完成，已写出 {} 条记录到 {}".format(len(results), OUTPUT_FILE))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        sys.exit(130)
