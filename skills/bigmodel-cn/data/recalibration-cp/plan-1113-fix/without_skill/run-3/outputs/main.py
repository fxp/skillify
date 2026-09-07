#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan 套餐额度调用 GLM，问一句话并打印回答。

为什么原来的代码报 429 / 1113「余额不足或无可用资源包」：

  智谱开放平台上「标准后付费 API」和「GLM Coding Plan 编程套餐」是两套
  互不相通的入口，Key 相同但端点不同：

    - 标准后付费（走账户余额 / 资源包）: https://open.bigmodel.cn/api/paas/v4
    - Coding Plan 套餐（走套餐额度）  : https://open.bigmodel.cn/api/coding/paas/v4
      （Anthropic 协议端点是 https://open.bigmodel.cn/api/anthropic，
        Codex/Responses 协议端点是 https://open.bigmodel.cn/api/v1）

  原代码打的是 /api/paas/v4，那条路只认账户余额，完全不看 Coding Plan 的
  套餐额度；账户里没充值余额，于是返回 1113。把端点换成
  /api/coding/paas/v4 就会从 Coding Plan 套餐里扣，不再报 1113。

模型名：Coding Plan 当前支持 glm-5.3 / glm-5.3-flash（以及 1M 上下文的
glm-5.3-flash[1m]）；历史模型 glm-5.2、glm-5.1 会自动路由到 glm-5.3。

只依赖 requests。
"""

import json
import os
import sys

import requests

# Coding Plan 专用端点（OpenAI Chat Completions 协议）。
# 千万不要换成 https://open.bigmodel.cn/api/paas/v4 —— 那是后付费端点，
# 不吃套餐额度，会报 1113。
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
ENDPOINT = BASE_URL + "/chat/completions"

MODEL = "glm-5.3"
PROMPT = "用一句话介绍 Python"
TIMEOUT = 120  # glm-5.3 默认开启思考，首字可能偏慢，超时给宽一点


def get_api_key() -> str:
    key = os.environ.get("GLM_KEY", "").strip()
    if not key:
        sys.exit("环境变量 GLM_KEY 未设置。请先执行：export GLM_KEY='你的智谱 API Key'")
    return key


def extract_text(data: dict) -> str:
    """从响应里取出正文。

    glm-5.3 是强制思考模型，思维链在 reasoning_content 里，最终答案在
    content 里。极少数情况下 content 为空（例如被 max_tokens 截断在思考
    阶段），这时退回到 reasoning_content，免得打印一个空行。
    """
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("响应里没有 choices 字段：" + json.dumps(data, ensure_ascii=False))

    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if content:
        return content

    reasoning = (message.get("reasoning_content") or "").strip()
    if reasoning:
        return reasoning

    raise ValueError("模型返回了空内容，finish_reason=%r" % choices[0].get("finish_reason"))


def main() -> None:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        # 简短问答不需要长思考，降低延迟；想要更强推理可改成 "high" / "max"
        "reasoning_effort": "low",
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer " + get_api_key(),
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        sys.exit("请求失败：%s" % exc)

    if resp.status_code != 200:
        # 把平台返回的原始报错打出来，比裸的 KeyError 好排查
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except ValueError:
            detail = resp.text
        hint = ""
        if '"1113"' in detail or "余额不足" in detail:
            hint = (
                "\n提示：仍然是 1113，说明这次请求没走到套餐额度上。请确认 "
                "(1) 端点是 /api/coding/paas/v4；"
                "(2) GLM_KEY 是购买了 Coding Plan 的那个账号的 Key；"
                "(3) 套餐处于生效期、当前时间窗额度未用尽。"
            )
        sys.exit("HTTP %d：%s%s" % (resp.status_code, detail, hint))

    try:
        text = extract_text(resp.json())
    except (ValueError, KeyError, TypeError) as exc:
        sys.exit("解析响应失败：%s" % exc)

    print(text)


if __name__ == "__main__":
    main()
