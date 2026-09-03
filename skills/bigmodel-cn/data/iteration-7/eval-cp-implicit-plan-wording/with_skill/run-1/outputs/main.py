#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）的 Key 直接通过 HTTP 调用 glm-5.3。

关键点：
- 套餐 Key 与开放平台按量付费 Key 是两套隔离的计费体系，Base URL 不同。
  套餐必须走  https://open.bigmodel.cn/api/coding/paas/v4  （注意多了 /coding）。
  打到标准端点 https://open.bigmodel.cn/api/paas/v4 会报 429 + 业务码 1113 "余额不足"，
  这不是让你充值，而是端点用错了。
- 鉴权是 HTTP Bearer：Authorization: Bearer <KEY>
- 套餐只包含 glm-5.3 / glm-5.3-flash 的对话能力。
"""

import os
import sys

import requests

# Coding Plan 专用端点（不是 /api/paas/v4）
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_COMPLETIONS_URL = f"{CODING_PLAN_BASE_URL}/chat/completions"

MODEL = "glm-5.3"
PROMPT = "用一句话介绍 Rust"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY（填 GLM Coding Plan 套餐的 Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        # glm-5.3 默认深度思考强度为 max；一句话的问题用 low 即可，响应更快、更省套餐额度
        "reasoning_effort": "low",
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        print(f"请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 常见错误：429 + {"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code, msg = err.get("code"), err.get("message")
        print(f"API 返回 HTTP {resp.status_code}，业务码 {code}：{msg or resp.text}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是真的余额不足。请确认：\n"
                "  1) ZHIPU_API_KEY 是 GLM Coding Plan 套餐 Key（bigmodel.cn/coding-plan/personal/overview 里创建的）；\n"
                "  2) 请求打的是 …/api/coding/paas/v4，而不是 …/api/paas/v4；\n"
                "  3) 模型是 glm-5.3 或 glm-5.3-flash；\n"
                "  4) 以上都对，才可能是 5 小时/每周套餐额度用完，等窗口刷新即可。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content") or ""

    if choice.get("finish_reason") not in (None, "stop", "length"):
        print(f"警告：finish_reason = {choice.get('finish_reason')}", file=sys.stderr)

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
