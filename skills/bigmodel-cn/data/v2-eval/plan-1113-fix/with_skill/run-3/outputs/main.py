"""用 GLM Coding Plan（编程套餐）Key 问 glm-5.3 一个问题并打印回答。

套餐 Key 必须打 Coding Plan 专用端点（…/api/coding/paas/v4）。
打标准端点（…/api/paas/v4）会报 429 + 1113「余额不足」——
那不是真要充值，是套餐额度在标准端点不可见。
"""

import os
import sys

import requests

# Coding Plan 专用 Base URL，比标准 API 多一层 /coding；路径里没有 /v1
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY（GLM Coding Plan 套餐的 API Key）")

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",  # 套餐各档位均支持
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=120,
    )

    if not resp.ok:
        # 1113「余额不足」通常意味着端点/能力/模型不在套餐范围内，而非真的缺钱
        sys.exit(f"HTTP {resp.status_code}: {resp.text}")

    print(resp.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
