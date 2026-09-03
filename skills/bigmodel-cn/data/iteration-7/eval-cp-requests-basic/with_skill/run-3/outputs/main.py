#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）Key 直接调 HTTP 接口，让 glm-5.3 用一句话介绍 Python。

依赖：requests（pip install requests）
环境变量：GLM_KEY —— 你的 GLM Coding Plan API Key（不是开放平台按量付费 Key）

注意：Coding Plan 的 Base URL 是 .../api/coding/paas/v4（多了 /coding），
用套餐 Key 打标准端点 .../api/paas/v4 会报 429 + 1113「余额不足」，那不是要充值，是端点错了。
"""

import os
import sys

import requests

# Coding Plan 专用端点：路径里有 /coding，且 v4 后面没有 /v1 这一级
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY（请填入 GLM Coding Plan 的 API Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Python"},
        ],
        "stream": False,
        # 不要把 max_tokens 设得太小：glm-5.3 默认开启深度思考，思考 token 也占输出额度
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(URL, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 典型错误：429 + {"error":{"code":"1113",...}} 说明 Key 与端点不匹配，
        # 或该能力/模型不在套餐内；1113 不代表需要充值。
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content")
    if not content:
        print(f"模型未返回文本，finish_reason={choice.get('finish_reason')}，原始响应：{data}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
