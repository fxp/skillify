#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）的 Key 直接通过 HTTP 调用 glm-5.3。

- 套餐 Key 必须打 Coding 端点 `https://open.bigmodel.cn/api/coding/paas/v4`，
  打标准端点 `…/api/paas/v4` 会报 HTTP 429 + 业务码 1113「余额不足」，这不是要充值。
- API Key 从环境变量 GLM_KEY 读取，不要硬编码。
- 运行：GLM_KEY=xxx python3 main.py
"""

import os
import sys

import requests

# 注意是 /api/coding/paas/v4，不是 /api/paas/v4；路径里也没有 /v1 这一级
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 套餐内可用模型：glm-5.3 / glm-5.3-flash


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（GLM Coding Plan 套餐的 API Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        "stream": False,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            API_URL,
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
        # 智谱错误体格式：{"error": {"code": "1113", "message": "..."}}
        try:
            err = resp.json().get("error", {})
            code, msg = err.get("code"), err.get("message")
        except ValueError:
            code, msg = None, resp.text
        print(f"HTTP {resp.status_code}，业务错误码 {code}：{msg}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是真的余额不足。请确认 GLM_KEY 是 Coding Plan 套餐 Key，"
                "且模型是 glm-5.3 / glm-5.3-flash；套餐 Key 不能用于 embeddings/生图等套餐外能力。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason not in (None, "stop", "length"):
        print(f"警告：finish_reason = {finish_reason}", file=sys.stderr)

    content = choice["message"].get("content") or ""
    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
