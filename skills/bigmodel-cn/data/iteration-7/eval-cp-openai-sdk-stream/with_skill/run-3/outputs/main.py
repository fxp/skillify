"""用 OpenAI 官方 SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行前：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py

注意：Coding Plan 的 Key 与开放平台按量付费 Key 不通用，Base URL 也不同：
    套餐   -> https://open.bigmodel.cn/api/coding/paas/v4   （多了 /coding）
    标准   -> https://open.bigmodel.cn/api/paas/v4
用套餐 Key 打标准端点会报 429 / 1113 "余额不足"，那不是要充值，是 Base URL 填错了。
"""

import os
import sys

from openai import OpenAI

BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）")

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "写一首关于秋天的四行小诗，只输出诗本身，不要标题和解释。"},
        ],
        stream=True,
    )

    for chunk in stream:
        # 最后一个 chunk 可能只带 usage、没有 choices，要先判空
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # glm-5.3-flash 默认开启深度思考，delta 里可能先出现 reasoning_content；
        # 这里只打印正文 content，忽略思维链
        if delta.content:
            print(delta.content, end="", flush=True)

    print()  # 流结束后换行


if __name__ == "__main__":
    main()
