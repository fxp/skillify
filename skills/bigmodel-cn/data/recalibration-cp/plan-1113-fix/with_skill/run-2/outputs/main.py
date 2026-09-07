#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）Key 调用 GLM 对话补全。

为什么原来的代码报 429 / 1113「余额不足或无可用资源包」：
智谱有两套彼此隔离的计费体系——按 token 计费的「标准 API」和按套餐额度
计费的「GLM Coding Plan」。两者的 Key 不通用、Base URL 也不同：

    标准 API      https://open.bigmodel.cn/api/paas/v4
    Coding Plan   https://open.bigmodel.cn/api/coding/paas/v4   <- 多了 /coding

套餐 Key 打到标准端点时，标准端点只看得到账户余额 / 资源包，看不到套餐额度，
于是返回 1113。这不是真的没额度，**不需要充值**，只要把 Base URL 换成
Coding 端点即可。
"""

import json
import os
import sys

import requests

# Coding Plan 专用端点（注意路径里的 /coding；不要再往后拼 /v1，否则 404）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_COMPLETIONS_URL = f"{BASE_URL}/chat/completions"

# 套餐档位（Lite / Pro / Max）都支持 glm-5.3 与 glm-5.3-flash。
# 其它老模型名会被静默路由到这两个之一，只写这两个最稳。
MODEL = "glm-5.3"

PROMPT = "用一句话介绍 Python"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print(
            "错误：未设置环境变量 GLM_KEY。\n"
            "请把 GLM Coding Plan 的 API Key（在 "
            "https://bigmodel.cn/coding-plan/personal/overview 创建）导出为：\n"
            "    export GLM_KEY=你的套餐Key",
            file=sys.stderr,
        )
        return 1

    try:
        resp = requests.post(
            CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": PROMPT}],
                "stream": False,
            },
            timeout=120,
        )
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 把服务端的原始错误打出来，方便区分「打错端点」和「真的没额度」
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except ValueError:
            detail = resp.text
        print(f"HTTP {resp.status_code}: {detail}", file=sys.stderr)
        if "1113" in detail:
            print(
                "提示：1113 在套餐场景下通常意味着 Key 与端点不匹配，或所请求的能力/模型不在套餐内。\n"
                f"当前端点：{CHAT_COMPLETIONS_URL}\n"
                "请确认 GLM_KEY 是 Coding Plan 套餐 Key（不是开放平台按量付费 Key），"
                "且模型为 glm-5.3 / glm-5.3-flash。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(
            f"响应结构非预期：{json.dumps(data, ensure_ascii=False)}",
            file=sys.stderr,
        )
        return 1

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
