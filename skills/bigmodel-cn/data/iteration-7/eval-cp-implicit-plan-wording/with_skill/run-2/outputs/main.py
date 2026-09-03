"""用 GLM Coding Plan（编程套餐）Key 直接走 HTTP 调 glm-5.3。

运行：ZHIPU_API_KEY=<你的套餐 Key> python3 main.py

注意：编程套餐（Lite / Pro / Max）走的是套餐额度，Base URL 必须是
    https://open.bigmodel.cn/api/coding/paas/v4
而不是按量付费的 https://open.bigmodel.cn/api/paas/v4。
套餐 Key 打标准端点会报 HTTP 429 + code 1113 "余额不足"，那不是让你充值，是端点用错了。
"""

import os
import sys

import requests

# Coding Plan 专用端点：比标准端点多一级 /coding，路径里没有 /v1
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3"  # 套餐内可用：glm-5.3 / glm-5.3-flash


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("请先设置环境变量 ZHIPU_API_KEY（填 GLM Coding Plan 套餐的 Key）", file=sys.stderr)
        return 1

    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "用一句话介绍 Rust"}],
            "stream": False,
            # glm-5.3 默认思考强度是 max；一句话问答用 low 省套餐额度
            "reasoning_effort": "low",
        },
        timeout=120,
    )

    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code, msg = err.get("code"), err.get("message", resp.text)
        print(f"请求失败：HTTP {resp.status_code} code={code} message={msg}", file=sys.stderr)
        if code == "1113":
            print(
                "提示：套餐 Key 报 1113 通常不是余额问题——请确认 ZHIPU_API_KEY 是在"
                " https://bigmodel.cn/coding-plan/personal/overview 创建的套餐 Key，"
                "且 Base URL 是 …/api/coding/paas/v4；或者 5 小时额度已用完，等窗口刷新。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    if choice.get("finish_reason") not in (None, "stop"):
        print(f"警告：finish_reason={choice.get('finish_reason')}", file=sys.stderr)
    print(choice["message"]["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
