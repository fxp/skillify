#!/usr/bin/env python3
"""
用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash，
让它写一首关于秋天的四行小诗，边收边打印，最后换行结束。

运行前：
    export GLM_CODING_PLAN_API_KEY="你的 Key"
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan 专用的 OpenAI 兼容端点（与普通 open.bigmodel.cn 的 /api/paas/v4 不同）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗。只输出诗句本身，不要标题和解释。"},
        ],
        stream=True,
    )

    for chunk in stream:
        # 部分 chunk（例如最后带 usage 的 chunk）可能没有 choices，需要跳过
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    # 结束后换行
    print()


if __name__ == "__main__":
    main()
