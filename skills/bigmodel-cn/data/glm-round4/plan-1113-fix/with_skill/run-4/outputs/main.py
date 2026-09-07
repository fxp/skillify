"""用 GLM Coding Plan 套餐 Key 调用 glm-5.3 问一句话并打印回答。

用法：GLM_KEY=你的套餐Key python3 main.py
"""

import os
import sys

import requests

# 套餐 Key 必须打 Coding 专用端点（多一级 /coding），
# 打标准端点 /api/paas/v4 会报 429 + 1113 "余额不足或无可用资源包"。
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("未设置环境变量 GLM_KEY，请先 export GLM_KEY=<你的 Coding Plan Key>")

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
        sys.exit(f"请求失败 HTTP {resp.status_code}: {resp.text}")

    print(resp.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
