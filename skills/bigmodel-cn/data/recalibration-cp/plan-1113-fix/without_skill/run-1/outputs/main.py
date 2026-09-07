#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan 套餐调用智谱 GLM，问一句话并打印回答。

关键点：Coding Plan（编程套餐）有自己的入口。
  - 标准后付费 API： https://open.bigmodel.cn/api/paas/v4        <- 走余额/资源包
  - Coding Plan   ： https://open.bigmodel.cn/api/coding/paas/v4 <- 走套餐额度
  - Anthropic 协议： https://open.bigmodel.cn/api/anthropic       （给 Claude Code 之类用）
用套餐的 Key 打标准后付费入口，就会得到 429 + code 1113
“余额不足或无可用资源包”——因为那条路只认账户余额，不认套餐。
"""

import json
import os
import sys

import requests

# Coding Plan 专用入口（OpenAI 兼容格式）
BASE_URL = os.environ.get(
    "GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"
).rstrip("/")
ENDPOINT = f"{BASE_URL}/chat/completions"

# Coding Plan 当前支持 glm-5.3 / glm-5.3-flash；历史型号会被自动路由过去
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")

PROMPT = "用一句话介绍 Python"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("环境变量 GLM_KEY 未设置，请先导出 Coding Plan 的 API Key。", file=sys.stderr)
        return 2

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        if '"1113"' in resp.text or "余额不足" in resp.text:
            print(
                "提示：1113 通常说明请求打到了后付费入口。确认 BASE_URL 是 "
                "https://open.bigmodel.cn/api/coding/paas/v4，且用的是 Coding Plan 的 Key。",
                file=sys.stderr,
            )
        return 1

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(f"返回不是合法 JSON：{resp.text[:500]}", file=sys.stderr)
        return 1

    if "error" in data:
        print(f"接口返回错误：{data['error']}", file=sys.stderr)
        return 1

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应结构不符合预期：{json.dumps(data, ensure_ascii=False)[:500]}", file=sys.stderr)
        return 1

    # 思考型模型可能把正文放在 content，推理过程放在 reasoning_content，这里只要正文
    if isinstance(content, list):  # 少数情况下是分段结构
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    print((content or "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
