#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM Coding Plan 的 HTTP 接口，让 glm-5.3 一句话介绍 Python。

用法:
    export GLM_KEY="你的 API Key"
    python3 main.py
"""

import os
import sys

import requests

# GLM Coding Plan 套餐使用专用的 coding 端点（与普通按量计费的 /api/paas/v4 不同）。
# 如需改用普通端点，可设置环境变量 GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY，请先 export GLM_KEY=你的APIKey", file=sys.stderr)
        return 1

    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Python"},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"错误：请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"错误：HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        print(f"错误：无法解析响应：{resp.text}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
