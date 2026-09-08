"""用 GLM Coding Plan 套餐 Key 调用 GLM 对话接口。

原代码报 429 + 1113（余额不足）的根因不是没额度，而是端点用错了：
套餐 Key 打标准端点 /api/paas/v4 必报 1113，必须改走 Coding 专用端点
/api/coding/paas/v4（模型 glm-5.3 / glm-5.3-flash 都在套餐内）。
"""

import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"  # 注意比标准端点多一层 /coding


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）")

    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        # 1113 = 余额不足或无可用资源包：套餐 Key 打了标准端点、能力/模型不在套餐内时都会报这个码。
        sys.exit(f"HTTP {resp.status_code}: {resp.text}")

    print(resp.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
