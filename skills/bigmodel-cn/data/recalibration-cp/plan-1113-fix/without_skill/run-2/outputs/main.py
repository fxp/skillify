#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）调用 GLM 模型，问一句话并打印回答。

关键点：Coding Plan 有自己**专属的**接口地址，必须用
    https://open.bigmodel.cn/api/coding/paas/v4
而不是通用的按量付费地址 https://open.bigmodel.cn/api/paas/v4 。
打到通用地址上时，套餐额度不会被识别，平台会去扣账户余额 / 资源包，
于是返回 429 + {"error": {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}}。

只依赖 requests，不需要其它第三方库。
"""

import json
import os
import sys

import requests

# Coding Plan（编程套餐）专属的 OpenAI 兼容端点
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"

MODEL = "glm-5.3"  # Coding Plan 支持的模型名，小写；也可换成 glm-5.3-flash 等
PROMPT = "用一句话介绍 Python"
TIMEOUT = 120


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY（智谱开放平台 API Key）。", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
    }

    try:
        resp = requests.post(CHAT_URL, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 把平台原始报错打出来，便于区分 1113（走错端点/额度）、1301（内容风控）等
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except ValueError:
            detail = resp.text
        print(f"HTTP {resp.status_code}: {detail}", file=sys.stderr)
        if '"1113"' in detail or "1113" in detail:
            print(
                "提示：1113 通常是请求打到了按量付费端点。"
                "确认 BASE_URL 为 https://open.bigmodel.cn/api/coding/paas/v4 ，"
                "且 GLM_KEY 是订阅了 Coding Plan 的那个账号的 API Key。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        print(f"返回结构异常：{json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        return 1

    # 思考型模型可能把正文放在 content，把思维链放在 reasoning_content
    content = (message.get("content") or "").strip()
    if not content:
        content = (message.get("reasoning_content") or "").strip()

    if not content:
        print(f"模型未返回内容：{json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
