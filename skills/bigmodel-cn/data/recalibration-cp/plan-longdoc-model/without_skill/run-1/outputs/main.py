#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 report.txt（公司内部项目评估报告），调用智谱 GLM 生成中文摘要并打印到 stdout。

走的是 GLM Coding Plan 编程套餐的专属端点（OpenAI 协议）：
    https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
注意这与后付费的通用端点 https://open.bigmodel.cn/api/paas/v4 不是同一个，
只有 /api/coding/... 这个前缀才会走套餐额度、不额外扣费。

依赖：只用 requests + 标准库。
运行：GLM_KEY=xxx python3 main.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# GLM Coding Plan 编程套餐的 OpenAI 协议端点（不是通用的 /api/paas/v4）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = BASE_URL + "/chat/completions"

# 套餐当前覆盖 glm-5.3 / glm-5.3-flash（旧版号 glm-4.7、glm-5.1、glm-5.2 会自动路由到新版）。
# 这篇报告不长，用完整版 glm-5.3 拿更稳的抽取质量；想更快更省可换成 glm-5.3-flash。
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")

REPORT_FILE = "report.txt"
TIMEOUT = (10, 300)  # (连接超时, 读取超时)；长文摘要生成慢，读超时给足
MAX_RETRIES = 3

SYSTEM_PROMPT = (
    "你是一名严谨的企业分析师，擅长把内部评估报告压缩成决策者能直接读的摘要。"
    "只依据给定原文作答，不得补充原文没有的数字、结论或假设；"
    "原文中出现的关键数字（金额、比例、周期、人数、阈值）必须原样保留，不要四舍五入或换算。"
)

USER_PROMPT_TEMPLATE = """请阅读下面这份公司内部的项目评估报告，写一段结构清晰的中文摘要。

摘要必须完整覆盖以下三个方面，每一部分都要带上原文中的具体数字：

1. 项目分为几个阶段：每个阶段的时长、目标和量化指标；
2. 技术选型的三条路线：分别是什么，各自的成本（金额、周期）和主要限制；
3. 财务上的止损条件：具体在什么时点、触发哪些指标会导致项目暂停或转入评估期。

写作要求：
- 用中文，分成上述三个小节，每节用一个小标题；
- 三个方面之外的重要硬约束（如风险、合规、人员）如有则在末尾用一两句话补充；
- 不要输出与报告无关的客套话、前言或后记；
- 直接输出摘要正文。

--- 报告原文开始 ---
{document}
--- 报告原文结束 ---
"""


def read_report() -> str:
    """读取与本脚本同目录下的 report.txt。"""
    path = Path(__file__).resolve().parent / REPORT_FILE
    if not path.is_file():
        sys.exit("错误：找不到报告文件 {}，请确认它与 main.py 在同一目录下。".format(path))

    # 内部文档偶尔带 BOM 或非 UTF-8 编码，逐个尝试，避免直接崩掉
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit("错误：无法解码 {}，请确认文件编码为 UTF-8 或 GB18030。".format(path))

    text = text.strip()
    if not text:
        sys.exit("错误：{} 是空文件，没有可摘要的内容。".format(path))
    return text


def get_api_key() -> str:
    key = os.environ.get("GLM_KEY", "").strip()
    if not key:
        sys.exit(
            "错误：环境变量 GLM_KEY 未设置。\n"
            "请先执行：export GLM_KEY='你的智谱 API Key'（Coding Plan 套餐对应的 Key）"
        )
    return key


def summarize(document: str, api_key: str) -> str:
    """调用 GLM 生成摘要，返回正文文本。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(document=document)},
        ],
        # 摘要任务要的是忠实复述而不是发挥，温度压低
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                CHAT_URL,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            last_error = "网络请求失败：{}".format(exc)
        else:
            if resp.status_code == 200:
                return extract_content(resp)

            detail = describe_error(resp)
            # 429（限流/套餐额度用尽的 5 小时窗口）和 5xx 值得重试，其余直接报错退出
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = detail
            else:
                sys.exit("错误：调用 GLM 接口失败。\n{}".format(detail))

        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(
                "第 {} 次调用失败（{}），{} 秒后重试……".format(attempt, last_error, wait),
                file=sys.stderr,
            )
            time.sleep(wait)

    sys.exit("错误：重试 {} 次后仍未成功。\n{}".format(MAX_RETRIES, last_error))


def describe_error(resp: "requests.Response") -> str:
    """把接口返回的错误整理成一句人能看懂的话。"""
    try:
        body = resp.json()
    except ValueError:
        return "HTTP {}：{}".format(resp.status_code, resp.text[:500])

    err = body.get("error") or {}
    code = err.get("code") or body.get("code")
    message = err.get("message") or body.get("message") or json.dumps(body, ensure_ascii=False)
    hint = ""
    if resp.status_code in (401, 403):
        hint = "\n提示：请检查 GLM_KEY 是否正确，以及该 Key 是否已开通 GLM Coding Plan 套餐。"
    elif resp.status_code == 429:
        hint = "\n提示：可能触发了套餐的 5 小时 / 每周用量上限，或并发限流。"
    return "HTTP {}（code={}）：{}{}".format(resp.status_code, code, message, hint)


def extract_content(resp: "requests.Response") -> str:
    """从 chat/completions 响应里取出正文（忽略思考链 reasoning_content）。"""
    try:
        body = resp.json()
    except ValueError:
        sys.exit("错误：接口返回的不是合法 JSON：{}".format(resp.text[:500]))

    choices = body.get("choices") or []
    if not choices:
        sys.exit("错误：接口返回中没有 choices 字段：{}".format(
            json.dumps(body, ensure_ascii=False)[:500]))

    message = choices[0].get("message") or {}
    content = message.get("content")

    # 部分模型/网关会把正文放在 content 的分块列表里，这里一并兼容
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
        content = "".join(parts)

    if not content or not str(content).strip():
        finish = choices[0].get("finish_reason")
        sys.exit(
            "错误：模型返回了空内容（finish_reason={}）。"
            "若为 length，请调大 max_tokens 后重试。".format(finish)
        )

    return str(content).strip()


def main() -> None:
    document = read_report()
    api_key = get_api_key()

    print(
        "正在用 {} 摘要 report.txt（{} 字）……".format(MODEL, len(document)),
        file=sys.stderr,
    )
    summary = summarize(document, api_key)

    print(summary)


if __name__ == "__main__":
    main()
