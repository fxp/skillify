#!/usr/bin/env python3
"""用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行前请设置环境变量：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
然后直接：
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan 的 OpenAI 兼容端点（注意路径里的 /coding/）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "写一首关于秋天的四行小诗。"},
        ],
        stream=True,
    )

    for chunk in stream:
        # 部分 chunk（如末尾带 usage 的）可能没有 choices，跳过即可
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    # 流结束后换行收尾
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
