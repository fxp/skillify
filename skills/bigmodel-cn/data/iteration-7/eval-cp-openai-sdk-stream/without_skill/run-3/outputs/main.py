#!/usr/bin/env python3
"""用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行方式:
    export GLM_CODING_PLAN_API_KEY="你的 key"
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan 专用的 OpenAI 兼容端点（与普通按量计费端点不同）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print(
            "错误：未找到环境变量 GLM_CODING_PLAN_API_KEY，请先设置后再运行。",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "请写一首关于秋天的四行小诗，只输出诗句本身。",
            }
        ],
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            print(content, end="", flush=True)

    print()  # 结束换行
    return 0


if __name__ == "__main__":
    sys.exit(main())
