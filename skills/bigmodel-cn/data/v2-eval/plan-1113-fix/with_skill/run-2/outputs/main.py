"""用 GLM Coding Plan（编程套餐）Key 调 GLM 对话接口。

关键点：套餐 Key 与标准 API Key 不通用，必须走 Coding 专用端点
（…/api/coding/paas/v4）。打到标准端点（…/api/paas/v4）会返回
429 + {"code": "1113", "message": "余额不足或无可用资源包"}——
那不是真的缺钱，是端点错了，不要去充值。

用法：
    export GLM_KEY="你的 Coding Plan API Key"
    python3 main.py
"""
import os
import sys

import requests

# 套餐专用的 OpenAI 兼容端点，比标准 API 多一级 /coding
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> int:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（GLM Coding Plan 的 API Key）", file=sys.stderr)
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
        # 429/1113 依旧出现时，按 端点->能力->模型 的顺序排查：
        # 确认这是套餐 Key、调的是 chat/completions、模型是 glm-5.3 / glm-5.3-flash
        print(f"请求失败：HTTP {resp.status_code} {resp.text}", file=sys.stderr)
        return 1

    print(resp.json()["choices"][0]["message"]["content"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
