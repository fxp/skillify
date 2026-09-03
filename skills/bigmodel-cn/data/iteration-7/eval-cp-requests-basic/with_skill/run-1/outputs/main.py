#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）的 Key，通过 requests 直接调 HTTP 接口，让 glm-5.3 用一句话介绍 Python。

用法：
    export GLM_KEY="你的 GLM Coding Plan API Key"
    python3 main.py

注意：Coding Plan 的 Key 和开放平台按量付费的 Key 是两套隔离的计费体系，
Base URL 必须用 https://open.bigmodel.cn/api/coding/paas/v4（多了 /coding 一级）。
如果打到标准端点 https://open.bigmodel.cn/api/paas/v4 会报 429 + 错误码 1113 "余额不足"，
那不是要充值，而是端点用错了。
"""

import os
import sys

import requests

# GLM Coding Plan 专用端点（OpenAI 兼容格式，请求体与标准端点完全一致）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_URL = f"{BASE_URL}/chat/completions"
MODEL = "glm-5.3"  # 套餐所有档位都支持 glm-5.3 / glm-5.3-flash


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY，请先执行 export GLM_KEY=<你的 Coding Plan API Key>", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        "stream": False,
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
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 智谱的错误体形如 {"error": {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}}
        try:
            err = resp.json().get("error", {})
            code, message = err.get("code"), err.get("message")
        except ValueError:
            code, message = None, resp.text
        print(f"接口返回 HTTP {resp.status_code}，错误码 {code}：{message}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是真的余额不足。请确认 GLM_KEY 是 GLM Coding Plan 套餐 Key"
                "（个人版在 https://bigmodel.cn/coding-plan/personal/overview 创建），"
                "并且请求打的是 /api/coding/paas/v4 端点；套餐 Key 打标准端点 /api/paas/v4 必定报 1113。",
                file=sys.stderr,
            )
        return 1

    try:
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        print(f"无法解析响应：{resp.text}", file=sys.stderr)
        return 1

    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
