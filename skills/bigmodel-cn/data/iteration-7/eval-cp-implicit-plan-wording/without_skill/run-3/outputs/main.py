#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM 编程套餐（Coding Plan）的 HTTP 接口。

注意：编程套餐（包月、按 5 小时额度计）的 Key 走的是专用的 coding 端点，
而不是按量付费的通用端点 /api/paas/v4，走错端点会报无权限/余额类错误。
"""

import os
import sys

import requests

# 编程套餐专用端点（OpenAI 兼容格式）
CODING_PLAN_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Rust"},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(CODING_PLAN_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应格式异常：{data}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
