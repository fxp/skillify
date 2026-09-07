#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 report.txt（公司内部项目评估报告），调用智谱 BigModel 生成中文摘要并打印到 stdout。

要点：
- 使用 GLM Coding Plan（编程套餐）的 OpenAI 兼容端点：
      https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
  注意：按量付费端点是 https://open.bigmodel.cn/api/paas/v4，两者不同；
  填错端点会走账户余额计费，而不是扣套餐额度。
- 模型用 glm-5.3（上下文 1M，足够整篇报告一次性喂进去，无需分块）。
  glm-5.3 强制开启思考，thinking.type 只能是 "enabled"；
  用 reasoning_effort 控制推理强度（low / high / max，默认 max）。
- API Key 从环境变量 GLM_KEY 读取。
- 仅依赖 requests。
"""

import json
import os
import sys

import requests

# GLM Coding Plan（编程套餐）专用端点，别写成按量付费的 /api/paas/v4
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = BASE_URL + "/chat/completions"
MODEL = "glm-5.3"
TIMEOUT = 300  # 秒；长文档 + 思考模型，超时给宽一点

SYSTEM_PROMPT = "你是一名严谨的商业分析助理，只根据给定材料作答，不臆造数字，输出简体中文。"

USER_PROMPT_TEMPLATE = """下面是一份公司内部的项目评估报告全文。请写一段中文摘要（约 400-600 字，连贯成段或分小标题均可）。

摘要必须明确覆盖以下三点，数字要与原文一致：
1. 项目一共分几个阶段，每个阶段的时间跨度和目标；
2. 技术选型的三条路线分别是什么，各自的成本；
3. 财务上的止损条件（触发什么指标、达到什么阈值就中止或回退）。

如果原文中某一项信息缺失，请直接说明"报告中未提及"，不要编造。

===== 报告全文开始 =====
{report}
===== 报告全文结束 =====
"""


def read_report(path):
    if not os.path.exists(path):
        sys.exit("找不到报告文件：%s（请把 report.txt 放在 main.py 同目录下）" % path)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        sys.exit("报告文件为空：%s" % path)
    return text


def summarize(api_key, report_text):
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(report=report_text)},
        ],
        # glm-5.3 不再支持 thinking.type = "disabled"，只能 enabled；
        # 摘要任务用 low 就够，速度快很多。
        "thinking": {"type": "enabled"},
        "reasoning_effort": "low",
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }

    try:
        resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        sys.exit("请求失败：%s" % exc)

    if resp.status_code != 200:
        sys.exit(
            "接口返回 HTTP %s：%s" % (resp.status_code, resp.text[:1000])
        )

    try:
        data = resp.json()
    except json.JSONDecodeError:
        sys.exit("返回内容不是合法 JSON：%s" % resp.text[:1000])

    if "error" in data and data.get("error"):
        sys.exit("接口报错：%s" % json.dumps(data["error"], ensure_ascii=False))

    choices = data.get("choices") or []
    if not choices:
        sys.exit("返回中没有 choices：%s" % json.dumps(data, ensure_ascii=False)[:1000])

    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if not content:
        # 极端情况下模型只吐了思考内容而没有正文
        content = (message.get("reasoning_content") or "").strip()
    if not content:
        sys.exit("模型没有返回正文内容：%s" % json.dumps(data, ensure_ascii=False)[:1000])

    usage = data.get("usage") or {}
    return content, usage


def main():
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY（智谱开放平台 API Key）")

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.txt")
    report_text = read_report(report_path)

    content, usage = summarize(api_key, report_text)

    print(content)
    if usage:
        print(
            "\n--- token 用量：prompt %s / completion %s / total %s ---"
            % (
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
            ),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
