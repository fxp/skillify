"""用 GLM Coding Plan（编程套餐）Key 调 GLM 对话接口。

关键点：套餐 Key 必须打 Coding Plan 专用端点（路径里多一级 /coding），
打标准端点 /api/paas/v4 会报 429 + 1113"余额不足"——那不是真缺钱，
是标准端点看不到套餐额度。
"""

import os
import sys

import requests

# Coding Plan 专用 Base URL，注意比标准 API 多了 /coding 这一段
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",  # 套餐支持的模型
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        # 把平台的错误码原样打出来，便于排查（如 1113 = 端点/模型不在套餐范围）
        print(f"请求失败 HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    answer = resp.json()["choices"][0]["message"]["content"]
    print(answer)


if __name__ == "__main__":
    main()
