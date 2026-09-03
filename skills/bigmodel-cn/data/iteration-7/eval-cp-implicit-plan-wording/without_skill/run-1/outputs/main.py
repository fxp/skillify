#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM 编程套餐（Coding Plan）的 HTTP 接口，让 glm-5.3 一句话介绍 Rust。

注意：编程套餐（包月、按 5 小时额度计）的 Key 只能走编程套餐专用网关
    https://open.bigmodel.cn/api/coding/paas/v4
而不是按量付费的通用网关 https://open.bigmodel.cn/api/paas/v4，
用错网关会报 401/1113 之类的余额或鉴权错误。
"""

import os
import sys

import requests

# 编程套餐专用的 OpenAI 兼容网关（注意路径里的 /coding/）
BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
MODEL = os.environ.get("ZHIPU_MODEL", "glm-5.3")


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY", file=sys.stderr)
        return 1

    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Rust"},
        ],
        # 编程套餐的模型默认可能开启“思考”模式，关闭以便直接拿到简短回答
        "thinking": {"type": "disabled"},
        "stream": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        print(f"请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应格式异常：{data}", file=sys.stderr)
        return 1

    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
