#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）Key 直接通过 HTTP 调用 glm-5.3。

关键点：
- 套餐 Key 必须打 Coding 端点 https://open.bigmodel.cn/api/coding/paas/v4，
  不能打标准端点 .../api/paas/v4，否则会报 HTTP 429 + 业务码 1113「余额不足」
  （这不是要充值，而是端点用错了）。
- 路径里没有 /v1 这一级，不要写成 .../coding/paas/v4/v1/chat/completions。
- 请求体与标准 chat/completions 完全一致。

运行：ZHIPU_API_KEY=你的套餐Key python3 main.py
"""

import os
import sys

import requests

# Coding Plan 专用端点（注意多了 /coding）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：请先设置环境变量 ZHIPU_API_KEY（GLM Coding Plan 套餐 Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Rust"}],
        "stream": False,
        # glm-5.3 默认深度思考；这种简单问题用 low 档更快、更省额度
        "reasoning_effort": "low",
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        print(f"网络请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 常见错误：429 + 1113 = 套餐 Key 打错端点 / 调用了套餐不含的模型或能力
        try:
            err = resp.json().get("error", {})
            code, msg = err.get("code"), err.get("message")
        except ValueError:
            code, msg = None, resp.text
        print(f"请求失败 HTTP {resp.status_code}，业务码 {code}：{msg}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是余额问题。请确认：1) ZHIPU_API_KEY 是 Coding Plan 套餐 Key；"
                "2) 端点是 .../api/coding/paas/v4；3) 模型是 glm-5.3 或 glm-5.3-flash。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content") or ""
    print(content.strip())

    finish = choice.get("finish_reason")
    if finish not in (None, "stop"):
        print(f"[finish_reason={finish}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
