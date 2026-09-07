#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）Key 调用 GLM 对话补全。

关键点：Coding Plan 与标准 API 是两套彼此隔离的计费体系，Key 不通用、
Base URL 也不同。套餐 Key 打标准端点 https://open.bigmodel.cn/api/paas/v4
会返回 HTTP 429 + {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}
——这不是真的没钱，而是标准端点根本看不到套餐额度。
正确的端点是 https://open.bigmodel.cn/api/coding/paas/v4（多了 /coding）。

只依赖 requests，无其它第三方库。
"""

import os
import sys

import requests

# 套餐端点：注意路径里的 /coding；末尾不要再拼 /v1，否则 404
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
ENDPOINT = f"{BASE_URL}/chat/completions"

# 套餐内稳定可用的模型只有 glm-5.3 和 glm-5.3-flash；
# 其它旧模型名要么被静默路由到这两个之一，要么直接报 1113。
MODEL = "glm-5.3"

PROMPT = "用一句话介绍 Python"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY（请填入 GLM Coding Plan 的 API Key）。", file=sys.stderr)
        print("套餐 Key 在 https://bigmodel.cn/coding-plan/personal/overview 创建。", file=sys.stderr)
        return 2

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
    }

    try:
        resp = requests.post(
            ENDPOINT,
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
        # 把服务端的原始错误打出来，便于按错误码排查
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        print(f"HTTP {resp.status_code}: {detail}", file=sys.stderr)

        code = ""
        if isinstance(detail, dict):
            code = str(detail.get("error", {}).get("code", ""))
        if code == "1113":
            print(
                "提示：1113 在套餐场景下通常不是余额问题。请依次核对："
                "① 手里的 Key 是不是 Coding Plan 套餐 Key；"
                f"② Base URL 是否为 {BASE_URL}；"
                "③ 模型是否为 glm-5.3 / glm-5.3-flash；"
                "④ 最后才考虑 5 小时 / 7 天额度窗口是否已用尽。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应结构异常：{data}", file=sys.stderr)
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
