#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度对同目录下的 report.txt 生成中文摘要。

关键点（来自智谱开放平台文档）：

1. 套餐 Key 和标准 API Key 是两套隔离的计费体系，Base URL 不同：
     - 标准 API：       https://open.bigmodel.cn/api/paas/v4
     - GLM Coding Plan：https://open.bigmodel.cn/api/coding/paas/v4   <- 本脚本用这个
   用套餐 Key 去打标准端点会返回 HTTP 429 + 业务码 1113「余额不足」，
   那不是真的没钱，而是端点选错了。
2. 套餐内只保证有 glm-5.3 / glm-5.3-flash 两个对话模型（其它模型代码会被静默
   路由或直接报 1113）。这里用 glm-5.3：1M 上下文、128K 最大输出，长文档不用切分。
3. Base URL 到 .../coding/paas/v4 为止，后面直接接 /chat/completions；
   多拼一层 /v1 会 404。
4. 合规提醒：官方条款写明「套餐仅限在官方支持的指定工具与产品环境中使用」
   （Claude Code、OpenCode、Cherry Studio 等）。自己写脚本调 Coding 端点技术上
   能通，但属于条款之外的用法；生产系统请改用标准 API Key + /api/paas/v4。

只依赖 requests，其余全部是标准库。
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# Coding Plan 专用端点（注意路径里的 /coding，且不要再加 /v1）
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 套餐内可用的对话模型：glm-5.3（1M 上下文 / 128K 输出）或 glm-5.3-flash
MODEL = "glm-5.3"

REPORT_PATH = Path(__file__).resolve().parent / "report.txt"

# 连接超时 / 读取超时。思考型模型 + 长文档，读超时给足。
TIMEOUT = (10, 600)

MAX_RETRIES = 4  # 仅对 429 / 5xx 做指数退避重试

PROMPT_TEMPLATE = """你是一名严谨的商业分析助手。请阅读下面这份公司内部的项目评估报告，
写一段结构清晰的中文摘要。

摘要必须明确覆盖以下三点，数字要与原文完全一致，不要臆造原文没有的信息：
1. 项目一共分为几个阶段，每个阶段的周期与目标；
2. 技术选型评估的三条路线分别是什么，各自的成本（金额、周期）与主要限制；
3. 财务上要求的止损条件（触发条件与触发后的处理）。

输出要求：用中文，分条陈述，总长度控制在 500 字以内，不要加与摘要无关的开场白。

<报告正文>
{report}
</报告正文>"""


def load_report() -> str:
    """读取同目录下的 report.txt。"""
    if not REPORT_PATH.exists():
        sys.exit(f"找不到报告文件：{REPORT_PATH}\n请把 report.txt 放在 main.py 同一个目录下。")
    text = REPORT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"报告文件是空的：{REPORT_PATH}")
    return text


def get_api_key() -> str:
    key = os.environ.get("GLM_KEY", "").strip()
    if not key:
        sys.exit(
            "环境变量 GLM_KEY 未设置。\n"
            "请填入 GLM Coding Plan 的套餐 Key（个人版在 "
            "https://bigmodel.cn/coding-plan/personal/overview 创建，团队版在"
            "「团队编程套餐 > 我的套餐」里取），然后：\n"
            "  export GLM_KEY='你的套餐 Key'"
        )
    return key


def explain_business_error(status_code: int, body: dict) -> str:
    """把智谱的业务错误码翻译成人话，特别是最容易踩的 1113。"""
    err = body.get("error") or {}
    code = str(err.get("code", ""))
    message = err.get("message", "")
    hint = ""
    if code == "1113":
        hint = (
            "\n提示：1113 有三种可能，按顺序排查——\n"
            f"  1) Base URL 是否就是 {API_URL}（套餐 Key 打标准的 /api/paas/v4 必报 1113）；\n"
            "  2) 用的能力是否在套餐内（embeddings / rerank / 生图 / 异步对话等都不在）；\n"
            f"  3) 模型 {MODEL} 是否在套餐内（套餐只保证 glm-5.3 / glm-5.3-flash）；\n"
            "  以上都没问题，才是套餐额度（5 小时档 / 每周档）确实用光了，等窗口刷新。"
        )
    elif code == "1210":
        hint = "\n提示：该模型强制思考，不能关闭，只能用 reasoning_effort 调节（low / high / max）。"
    elif code in ("1302", "1305", "1308", "1310"):
        hint = "\n提示：触发限流或用量上限，请降低并发并退避重试。"
    elif code in ("1001", "1002", "1003", "1004"):
        hint = "\n提示：鉴权失败，检查 GLM_KEY 是否正确、是否已过期。"
    return f"调用失败：HTTP {status_code}，错误码 {code or '未知'}：{message}{hint}"


def call_glm(api_key: str, report: str) -> dict:
    """调用 Coding Plan 端点，带指数退避重试，返回解析后的 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": PROMPT_TEMPLATE.format(report=report)},
        ],
        # glm-5.3 始终思考，只能调强度。摘要属于轻量任务，用 low 省套餐额度。
        "reasoning_effort": "low",
        "max_tokens": 4096,
        # 摘要要稳定复现，走贪心解码（此时 temperature / top_p 被忽略）。
        "do_sample": False,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"网络请求异常：{exc}"
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                print(f"[重试] {last_error}，{wait}s 后重试…", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(last_error)

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                sys.exit(f"响应不是合法 JSON：{resp.text[:500]}")

        try:
            body = resp.json()
        except ValueError:
            body = {}

        code = str((body.get("error") or {}).get("code", ""))
        message = explain_business_error(resp.status_code, body) if body else (
            f"调用失败：HTTP {resp.status_code}，响应：{resp.text[:500]}"
        )

        # 1113 是配置/额度问题，重试没有意义；其余 429 与 5xx 才退避重试。
        retriable = resp.status_code >= 500 or (resp.status_code == 429 and code != "1113")
        if retriable and attempt < MAX_RETRIES - 1:
            wait = 2 ** attempt
            print(f"[重试] {message}\n{wait}s 后重试…", file=sys.stderr)
            time.sleep(wait)
            continue
        sys.exit(message)

    sys.exit(last_error or "重试次数用尽，调用失败。")


def extract_summary(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        sys.exit(f"响应里没有 choices，原始响应：{json.dumps(data, ensure_ascii=False)[:800]}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "sensitive":
        sys.exit("内容被安全策略拦截（finish_reason=sensitive），请检查报告内容。")
    if finish_reason == "model_context_window_exceeded":
        sys.exit("报告超出模型上下文窗口，请先分段再分别摘要。")

    content = (choice.get("message") or {}).get("content") or ""
    content = content.strip()
    if not content:
        sys.exit(f"模型返回了空内容，原始响应：{json.dumps(data, ensure_ascii=False)[:800]}")

    if finish_reason == "length":
        print("[警告] 输出达到 max_tokens 上限，摘要可能被截断。", file=sys.stderr)
    return content


def main() -> None:
    report = load_report()
    api_key = get_api_key()
    data = call_glm(api_key, report)
    print(extract_summary(data))

    usage = data.get("usage") or {}
    if usage:
        print(
            "\n---\n"
            f"model={data.get('model', MODEL)} "
            f"prompt_tokens={usage.get('prompt_tokens')} "
            f"completion_tokens={usage.get('completion_tokens')} "
            f"total_tokens={usage.get('total_tokens')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
