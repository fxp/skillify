#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan 套餐 Key 调用 GLM 对话接口，问一句话并打印回答。

关键点（也是原代码报 1113 的原因）：
智谱有两套彼此隔离的计费体系——
  * 标准 API（按 token / 资源包计费）: https://open.bigmodel.cn/api/paas/v4
  * GLM Coding Plan 编程套餐（按套餐额度计费）: https://open.bigmodel.cn/api/coding/paas/v4
套餐 Key 打标准端点时，标准端点只看账户余额/资源包，看不到套餐额度，
于是返回 HTTP 429 + {"error": {"code": "1113", "message": "余额不足或无可用资源包,请充值。"}}。
这不是真的没额度，**不需要充值**，把 Base URL 换成带 /coding 的那条即可。
"""

import os
import sys

import requests

# 套餐端点：注意路径里多了一级 /coding，且到 /v4 为止（不要再拼 /v1）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
ENDPOINT = f"{BASE_URL}/chat/completions"

# 套餐内稳定可用的模型只有 glm-5.3 / glm-5.3-flash（其他旧模型名会被隐式路由或直接报 1113）
MODEL = "glm-5.3"

PROMPT = "用一句话介绍 Python"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("未找到环境变量 GLM_KEY，请先 export GLM_KEY=<你的 Coding Plan API Key>", file=sys.stderr)
        return 2

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        # glm-5.3 默认强制深度思考，简单问答用 low 档省时间和额度
        "reasoning_effort": "low",
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
        print(f"请求失败: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 常见错误码提示，尤其是 1113
        detail = resp.text
        try:
            code = resp.json().get("error", {}).get("code")
        except ValueError:
            code = None
        print(f"HTTP {resp.status_code}: {detail}", file=sys.stderr)
        if code == "1113":
            print(
                "错误码 1113 在这里通常不是真的欠费，按顺序排查：\n"
                "  1) Key 是不是 Coding Plan 套餐 Key（个人版在 bigmodel.cn/coding-plan/personal/overview 创建，"
                "团队版用团队套餐 Key，与平台 Key 不通用）；\n"
                f"  2) Base URL 是不是 {BASE_URL}（套餐 Key 打标准的 /api/paas/v4 必报 1113）；\n"
                "  3) 模型是不是 glm-5.3 / glm-5.3-flash（glm-4-long、codegeex-4 等不在套餐内）；\n"
                "  4) 以上都对再考虑 5 小时 / 每周额度窗口是否已用尽，等窗口刷新，别重试风暴。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应格式异常: {data}", file=sys.stderr)
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
