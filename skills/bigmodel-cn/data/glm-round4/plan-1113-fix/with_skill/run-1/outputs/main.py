"""用 GLM Coding Plan（编程套餐）Key 问模型一句话并打印回答。

排错记录：套餐 Key 打标准端点 /api/paas/v4 会报 429 + 1113「余额不足」，
因为标准端点只认账户余额/资源包，看不到套餐额度。
套餐 Key 必须走 Coding Plan 专用端点 /api/coding/paas/v4（模型 glm-5.3 / glm-5.3-flash）。
"""
import os
import sys

import requests

URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY。请先 export GLM_KEY=<你的 Coding Plan API Key>", file=sys.stderr)
        return 1

    resp = requests.post(
        URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        # 1113 = Key 与端点/能力不匹配（打错端点、能力不在套餐内等），不是单纯"欠费"
        print(f"请求失败：HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        return 1

    print(resp.json()["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
