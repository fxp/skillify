"""用 GLM Coding Plan(编程套餐)Key 调 glm-5.3 并把回答打印到 stdout。

关键点:Coding Plan 的 Key 与标准 API 计费体系隔离,只能打专属端点
https://open.bigmodel.cn/api/coding/paas/v4;打到标准端点 .../api/paas/v4
会返回 429 + 1113「余额不足」,这不是真的缺钱,换端点即可。
"""

import os
import sys

import requests

URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        sys.exit("环境变量 GLM_KEY 未设置,请先 export GLM_KEY=<你的 Coding Plan API Key>")

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
