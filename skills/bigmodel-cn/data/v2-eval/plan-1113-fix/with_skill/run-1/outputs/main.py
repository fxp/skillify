"""用 GLM Coding Plan（编程套餐）Key 调 GLM 对话接口。

套餐 Key 与标准 API Key 不通用：套餐 Key 打标准端点 /api/paas/v4 会报
429 + 1113「余额不足」，必须走 Coding 端点 /api/coding/paas/v4。
"""

import os
import sys

import requests

# Coding Plan 专用 Base URL：比标准端点多一级 /coding，路径里没有 /v1
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）")

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",  # 套餐支持的模型；另一个是 glm-5.3-flash
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
            "stream": False,
            # Coding 端点默认开思考，思考 token 也计入 max_tokens，预算给足
            "max_tokens": 1024,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        # 把状态码和响应体打出来，方便区分 1113（端点/额度）与其他错误
        sys.exit(f"请求失败 HTTP {resp.status_code}: {resp.text}")

    answer = resp.json()["choices"][0]["message"]["content"]
    print(answer)


if __name__ == "__main__":
    main()
