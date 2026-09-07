#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 GLM Coding Plan（编程套餐）额度对同目录下的 report.txt 做中文摘要。

要点（来自智谱开放平台文档）：
  * 套餐 Key 与标准平台 Key 是两套隔离的计费体系，Base URL 不同：
        标准 API      https://open.bigmodel.cn/api/paas/v4
        Coding Plan   https://open.bigmodel.cn/api/coding/paas/v4   <- 本脚本用这个
    套餐 Key 打标准端点会返回 HTTP 429 + 业务码 1113「余额不足」，
    那不是真的要充值，而是 Base URL 用错了。
  * Base URL 只到 .../coding/paas/v4，后面直接拼 /chat/completions，
    中间没有 /v1 这一级（拼成 .../v4/v1/chat/completions 会 404）。
  * 套餐内可用的对话模型是 glm-5.3 / glm-5.3-flash。glm-5.3 是 1M 上下文、
    128K 最大输出，处理长文档足够；其它模型（embedding / rerank / 生图等）
    不在套餐内，同样会报 1113。
  * 注意：官方条款规定套餐额度「仅限在官方支持的指定工具与产品环境中使用」。
    自己写脚本调 Coding 端点技术上能通，但属于条款之外的用法；
    生产系统请改用标准 API Key + https://open.bigmodel.cn/api/paas/v4。

只依赖 requests，直接 `python3 main.py` 运行。
"""

import json
import os
import sys
import time

import requests

# Coding Plan 专用 Base URL（注意多了 /coding，且到 v4 为止）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_ENDPOINT = BASE_URL + "/chat/completions"

# 套餐内可用的旗舰对话模型：1M 上下文，长文档够用
MODEL = "glm-5.3"

# 生成长度上限（只限制输出，不含输入）。glm-5.3 默认 65536、上限 131072，
# 摘要场景显式给个小值即可，避免模型跑太长。
MAX_TOKENS = 2048

REQUEST_TIMEOUT = 300  # 秒；长文档 + 思考模式响应会比较慢
MAX_RETRIES = 3

SYSTEM_PROMPT = (
    "你是一名严谨的商业分析助理。你只根据用户提供的原始文档作答，"
    "不得编造文档中没有的数字、时间或结论。所有输出使用简体中文。"
)

USER_PROMPT_TEMPLATE = """下面是一份公司内部的项目评估报告，请阅读全文后写一段中文摘要。

摘要必须完整覆盖以下三个方面，缺一不可：
1. 项目一共分为几个阶段，每个阶段的时长/目标分别是什么；
2. 技术选型评估了哪三条路线，以及每条路线对应的成本（含金额与周期）；
3. 财务上给出的止损条件是什么（触发条件与触发后的处置方式）。

写作要求：
- 用连贯的中文段落或带小标题的分点表述，总长度控制在 400-600 字；
- 涉及数字（人数、比例、金额、周期、分数线）时必须与原文一致，不要四舍五入或改写；
- 只依据下面的报告内容，不要补充报告里没有的建议或推断。

===== 报告原文开始 =====
{document}
===== 报告原文结束 ====="""


def read_report(path):
    """读取同目录下的 report.txt。"""
    if not os.path.isfile(path):
        sys.exit(
            "找不到报告文件：%s\n"
            "请把待摘要的 report.txt 放在与 main.py 相同的目录下。" % path
        )
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        sys.exit("报告文件是空的：%s" % path)
    return text


def get_api_key():
    key = os.environ.get("GLM_KEY", "").strip()
    if not key:
        sys.exit(
            "环境变量 GLM_KEY 未设置。\n"
            "请填入 GLM Coding Plan（编程套餐）的 API Key，"
            "个人版在 https://bigmodel.cn/coding-plan/personal/overview 创建：\n"
            "    export GLM_KEY=你的套餐Key"
        )
    return key


def explain_http_error(resp):
    """把智谱的错误响应翻译成人话，重点区分 1113 的两种成因。"""
    try:
        body = resp.json()
    except ValueError:
        return "HTTP %s：%s" % (resp.status_code, resp.text[:500])

    err = body.get("error") or {}
    code = str(err.get("code", ""))
    message = err.get("message", json.dumps(body, ensure_ascii=False)[:500])

    if code == "1113":
        return (
            "HTTP %s，业务码 1113：%s\n"
            "这个错误码有三种常见成因，按顺序排查：\n"
            "  1) Key 与 Base URL 不匹配 —— 本脚本已使用 Coding Plan 端点 %s，"
            "如果 GLM_KEY 里放的是标准平台 Key，请改用 "
            "https://open.bigmodel.cn/api/paas/v4；\n"
            "  2) 请求的模型不在套餐内 —— 套餐只含 glm-5.3 / glm-5.3-flash；\n"
            "  3) 套餐额度用尽 —— 额度每 5 小时 / 每 7 天滚动重置，等窗口刷新即可，"
            "不需要给账户充值。" % (resp.status_code, message, BASE_URL)
        )
    if code == "1210":
        return (
            "HTTP %s，业务码 1210：%s\n"
            "glm-5.3 系列不支持关闭思考，只能用 reasoning_effort 调节强度。"
            % (resp.status_code, message)
        )
    if code:
        return "HTTP %s，业务码 %s：%s" % (resp.status_code, code, message)
    return "HTTP %s：%s" % (resp.status_code, message)


def summarize(document, api_key):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(document=document),
            },
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        # glm-5.3 在标准端点强制思考，只能调强度；摘要任务用 low 即可，省额度也更快。
        "reasoning_effort": "low",
    }
    headers = {
        "Authorization": "Bearer " + api_key,  # 智谱统一 HTTP Bearer 鉴权
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                CHAT_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = "网络请求失败：%s" % exc
        else:
            if resp.status_code == 200:
                return parse_completion(resp.json())

            last_error = explain_http_error(resp)

            # 429 里既可能是限流，也可能是 1113（额度/端点问题）。
            # 1113 重试没有意义，直接失败；其余 429 / 5xx 做退避重试。
            if "1113" in last_error or not (
                resp.status_code == 429 or resp.status_code >= 500
            ):
                sys.exit(last_error)

        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            sys.stderr.write(
                "第 %d 次调用失败，%d 秒后重试……（%s）\n"
                % (attempt, backoff, last_error.splitlines()[0])
            )
            time.sleep(backoff)

    sys.exit("重试 %d 次后仍然失败：%s" % (MAX_RETRIES, last_error))


def parse_completion(body):
    choices = body.get("choices") or []
    if not choices:
        sys.exit("响应里没有 choices 字段：%s" % json.dumps(body, ensure_ascii=False)[:500])

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    message = choice.get("message") or {}
    # 只取 content；reasoning_content 是思维链，不属于摘要正文。
    content = (message.get("content") or "").strip()

    if finish_reason == "sensitive":
        sys.exit("响应被内容安全策略拦截（finish_reason=sensitive）。")
    if finish_reason == "model_context_window_exceeded":
        sys.exit(
            "文档超出模型上下文窗口（%s 支持 1M tokens）。"
            "请先把 report.txt 分段后分别摘要再合并。" % MODEL
        )
    if finish_reason == "network_error":
        sys.exit("模型推理异常（finish_reason=network_error），请稍后重试。")
    if not content:
        sys.exit("模型没有返回正文内容（finish_reason=%s）。" % finish_reason)

    if finish_reason == "length":
        sys.stderr.write(
            "提示：输出达到 max_tokens=%d 被截断，可调大 MAX_TOKENS。\n" % MAX_TOKENS
        )
    return content, body.get("usage") or {}


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(script_dir, "report.txt")

    document = read_report(report_path)
    api_key = get_api_key()

    summary, usage = summarize(document, api_key)

    print(summary)

    if usage:
        sys.stderr.write(
            "\n[用量] prompt_tokens=%s completion_tokens=%s total_tokens=%s（模型 %s，走 Coding Plan 套餐额度）\n"
            % (
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
                MODEL,
            )
        )


if __name__ == "__main__":
    main()
