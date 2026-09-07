"""用 GLM Coding Plan 套餐额度调用 glm-5.3（修复 1113 报错）。

原代码报 429 + 1113「余额不足」的根因：套餐 Key 打到了标准 API 端点
（…/api/paas/v4）。标准端点只认账户余额/资源包，看不到套餐额度。
Coding Plan 套餐必须走专用端点 …/api/coding/paas/v4，无需充值。

用法：export GLM_KEY=你的套餐APIKey && python3 main.py
"""

import os
import sys

import requests

# Coding Plan 专用端点：比标准 API 多一层 /coding
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 GLM_KEY。请先 export GLM_KEY=你的套餐APIKey")

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    print(resp.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
