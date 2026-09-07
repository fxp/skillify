#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱 GLM 模型把每条反馈
抽取成结构化信息，写出同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
  - name:       反馈人姓名
  - issue_type: 问题类型（由模型自行归类）
  - urgency:    紧急程度，只能是 low / medium / high

依赖：仅 requests（标准库之外）。
用法：
    export ZHIPUAI_API_KEY="你的key"
    python3 main.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------- 配置

BASE_URL = os.environ.get(
    "ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
).rstrip("/")
CHAT_URL = BASE_URL + "/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")

TIMEOUT = 120          # 单次请求超时（秒）
MAX_RETRIES = 3        # 单条反馈最多重试次数
RETRY_BACKOFF = 2.0    # 重试退避基数（秒）

ALLOWED_URGENCY = ("low", "medium", "high")

HERE = Path(__file__).resolve().parent
INPUT_FILE = HERE / "feedback.txt"
OUTPUT_FILE = HERE / "out.json"

SYSTEM_PROMPT = """你是一个客户反馈信息抽取器。

给你一条客户反馈原文，你需要抽取出结构化信息，并且只输出一个 JSON 对象，
不要输出任何解释、前后缀或 Markdown 代码块。

JSON 对象必须恰好包含以下三个键：
1. "name": 字符串，反馈人的姓名。如果原文中没有出现姓名，填 "unknown"。
2. "issue_type": 字符串，你自己对问题类型的归类（简短的中文短语，例如
   "物流延迟"、"产品质量"、"退款问题"、"客服态度"、"账号登录"、"计费错误"、
   "功能建议" 等）。同类问题请尽量使用一致的措辞。
3. "urgency": 字符串，紧急程度，只能是 "low"、"medium"、"high" 三者之一。
   - high:   涉及资金损失、服务完全不可用、安全问题、客户明确表示要投诉/退款/流失。
   - medium: 影响正常使用但有变通方式，或客户明显不满但未升级。
   - low:    一般咨询、建议、轻微不便、表扬。

输出示例（仅示意格式）：
{"name": "张三", "issue_type": "物流延迟", "urgency": "medium"}"""


# ---------------------------------------------------------------- 工具函数


def die(msg):
    print("错误：" + msg, file=sys.stderr)
    sys.exit(1)


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die("环境变量 ZHIPUAI_API_KEY 未设置。请先执行：\n"
            '  export ZHIPUAI_API_KEY="你的智谱 API Key"')
    return key


def read_feedback():
    if not INPUT_FILE.exists():
        die("找不到输入文件：%s" % INPUT_FILE)
    text = INPUT_FILE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def extract_json_object(raw):
    """从模型返回的文本里尽量稳妥地取出一个 JSON 对象。"""
    if raw is None:
        return None
    s = raw.strip()

    # 去掉可能的 ```json ... ``` 包裹
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.S)
    if fence:
        s = fence.group(1).strip()

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
    except (ValueError, TypeError):
        pass

    # 兜底：截取第一个 { 到最后一个 } 之间的内容
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            pass
    return None


def normalize(obj, fallback_line):
    """把模型输出规整成恰好三个键，并保证 urgency 合法。"""
    obj = obj if isinstance(obj, dict) else {}

    name = obj.get("name")
    name = str(name).strip() if name not in (None, "") else "unknown"

    issue_type = obj.get("issue_type")
    issue_type = str(issue_type).strip() if issue_type not in (None, "") else "其他"

    urgency = str(obj.get("urgency", "")).strip().lower()
    if urgency not in ALLOWED_URGENCY:
        # 常见的近义写法做一次映射，其余落到 medium
        mapping = {
            "低": "low", "中": "medium", "高": "high",
            "urgent": "high", "critical": "high", "严重": "high",
            "normal": "medium", "moderate": "medium", "中等": "medium",
            "minor": "low", "轻微": "low",
        }
        urgency = mapping.get(urgency, "medium")

    del fallback_line  # 仅用于可能的调试，这里不参与输出
    return {"name": name, "issue_type": issue_type, "urgency": urgency}


def call_model(session, api_key, feedback_line):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "客户反馈原文：\n" + feedback_line},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
        # 抽取任务不需要思维链，关掉可以更快更省
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(
                CHAT_URL,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    last_err = "响应里没有 choices：%s" % json.dumps(
                        data, ensure_ascii=False)[:300]
                else:
                    content = (choices[0].get("message") or {}).get("content")
                    obj = extract_json_object(content)
                    if obj is not None:
                        return obj
                    last_err = "无法从模型输出解析出 JSON：%r" % (content,)
            elif resp.status_code in (429, 500, 502, 503, 504):
                last_err = "HTTP %s: %s" % (resp.status_code, resp.text[:300])
            else:
                # 4xx（鉴权、余额、参数等）通常重试也没用
                raise RuntimeError(
                    "HTTP %s: %s" % (resp.status_code, resp.text[:500]))
        except requests.RequestException as exc:
            last_err = "网络异常：%s" % exc

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * attempt)

    raise RuntimeError(last_err or "未知错误")


# ---------------------------------------------------------------- 主流程


def main():
    api_key = get_api_key()
    lines = read_feedback()
    if not lines:
        print("feedback.txt 为空，写出空数组。")
        OUTPUT_FILE.write_text("[]\n", encoding="utf-8")
        return

    print("共读取 %d 条反馈，使用模型 %s。" % (len(lines), MODEL))

    results = []
    session = requests.Session()
    for idx, line in enumerate(lines, 1):
        preview = line if len(line) <= 40 else line[:40] + "…"
        print("[%d/%d] %s" % (idx, len(lines), preview))
        try:
            obj = call_model(session, api_key, line)
        except Exception as exc:  # noqa: BLE001 - 单条失败不阻断整体
            print("    抽取失败，使用兜底值：%s" % exc, file=sys.stderr)
            obj = {}
        results.append(normalize(obj, line))

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("已写出 %d 条结果到 %s" % (len(results), OUTPUT_FILE))


if __name__ == "__main__":
    main()
