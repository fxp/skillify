#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 GLM Coding Plan（编程套餐）额度给 report.txt 生成中文摘要。

关键点（智谱开放平台 bigmodel.cn）：
  * 套餐 Key 与标准 API Key 是两套隔离的计费体系，Base URL 不同：
      标准 API      https://open.bigmodel.cn/api/paas/v4
      Coding Plan   https://open.bigmodel.cn/api/coding/paas/v4   <-- 本脚本用这个
    套餐 Key 打标准端点会返回 HTTP 429 + 错误码 1113「余额不足」，
    这不是真的要充值，而是端点用错了。
  * 套餐只覆盖部分模型：glm-5.3 / glm-5.3-flash 可用；
    glm-4-long / charglm-4 / codegeex-4 等即使名字看起来"适合长文本"，
    用套餐 Key 调用同样会返回 1113。所以这里固定用 glm-5.3
    （1M 上下文，处理这种长度的报告绰绰有余）。
  * 只依赖 requests，无其它第三方库。
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# Coding Plan 专用端点：注意路径里多了 /coding，且结尾就到 /v4，不要再拼 /v1
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"

# 套餐内可用的模型。不要用 glm-4-long（不在套餐内，会报 1113）
MODEL = "glm-5.3"

REPORT_FILENAME = "report.txt"
TIMEOUT = 180
MAX_RETRIES = 3

PROMPT_TEMPLATE = """你是一位企业项目分析师。请阅读下面这份公司内部的项目评估报告，用中文写一段结构清晰的摘要。

摘要必须明确覆盖以下三个方面，缺一不可：
1. 项目一共分为几个阶段推进，每个阶段的时长和目标分别是什么；
2. 技术选型评估了哪三条路线，以及每条路线对应的成本（金额与周期）；
3. 财务上要求的止损条件是什么（触发止损的具体指标和数值）。

要求：直接输出摘要正文，不要复述本提示词，不要加"以下是摘要"之类的开场白；
可以分条陈述，务必保留报告中的关键数字。

===== 报告原文开始 =====
{document}
===== 报告原文结束 =====
"""


def find_report() -> Path:
    """优先找脚本同目录下的 report.txt，其次找当前工作目录。"""
    candidates = [
        Path(__file__).resolve().parent / REPORT_FILENAME,
        Path.cwd() / REPORT_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        f"错误：找不到 {REPORT_FILENAME}。已尝试："
        + "、".join(str(p) for p in candidates)
    )


def read_api_key() -> str:
    key = (os.environ.get("GLM_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "错误：环境变量 GLM_KEY 未设置。\n"
            "请先导出 GLM Coding Plan 套餐 Key："
            "export GLM_KEY='你的套餐Key'\n"
            "（套餐 Key 在 https://bigmodel.cn/coding-plan/personal/overview 创建，"
            "与开放平台按量付费的 Key 不通用。）"
        )
    return key


def summarize(document: str, api_key: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT_TEMPLATE.format(document=document)}
        ],
        "stream": False,
        # glm-5.3 在标准端点强制思考，只能调强度；摘要任务用 low 足够，也更省套餐额度
        "reasoning_effort": "low",
        "temperature": 0.2,
        "max_tokens": 8192,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                CHAT_URL, headers=headers, json=payload, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = f"网络请求失败：{exc}"
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
                continue
            raise SystemExit(f"错误：{last_error}")

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                raise SystemExit(f"错误：响应不是合法 JSON：{resp.text[:500]}")
            message = (data.get("choices") or [{}])[0].get("message") or {}
            content = (message.get("content") or "").strip()
            if not content:
                # 极少数情况下正文为空但思考链里有内容，兜底取一下
                content = (message.get("reasoning_content") or "").strip()
            if not content:
                raise SystemExit(f"错误：模型返回了空内容：{json.dumps(data)[:500]}")
            return content

        # 非 200：把智谱的错误码解出来，给出可操作的提示
        detail = resp.text[:800]
        code = ""
        try:
            code = str(((resp.json() or {}).get("error") or {}).get("code", ""))
        except ValueError:
            pass

        if code == "1113":
            raise SystemExit(
                "错误：返回 1113。对套餐 Key 来说这通常不是真的余额不足，而是"
                f"端点或模型用错了。请确认 Base URL 是 {BASE_URL}（带 /coding），"
                f"且模型在套餐内（glm-5.3 / glm-5.3-flash）。当前用的是 {MODEL}。"
            )

        # 429 / 5xx 之类可能是限流或临时故障，退避重试
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            last_error = f"HTTP {resp.status_code}：{detail}"
            time.sleep(3 * attempt)
            continue

        raise SystemExit(f"错误：HTTP {resp.status_code}，响应：{detail}")

    raise SystemExit(f"错误：重试 {MAX_RETRIES} 次后仍失败。{last_error}")


def main() -> int:
    report_path = find_report()
    document = report_path.read_text(encoding="utf-8").strip()
    if not document:
        raise SystemExit(f"错误：{report_path} 是空文件。")

    api_key = read_api_key()
    summary = summarize(document, api_key)

    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
