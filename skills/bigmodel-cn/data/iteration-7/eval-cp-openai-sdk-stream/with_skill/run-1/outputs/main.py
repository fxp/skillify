"""用 OpenAI 官方 SDK 以流式方式调用智谱 GLM Coding Plan（glm-5.3-flash）写一首秋天小诗。

运行：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan（编程套餐）专用 Base URL：比标准 API 多了 /coding 这一级。
# 套餐 Key 打标准端点 https://open.bigmodel.cn/api/paas/v4 会报 1113「余额不足」，不是要充值。
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print(
            "错误：未设置环境变量 GLM_CODING_PLAN_API_KEY。\n"
            "请先执行：export GLM_CODING_PLAN_API_KEY='你的 GLM Coding Plan 套餐 Key'",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(api_key=api_key, base_url=CODING_PLAN_BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗，只输出诗句本身，不要标题和解释。"},
        ],
        stream=True,
        temperature=0.8,
        # glm-5.3-flash 默认强制开启深度思考，写小诗用不上，把推理强度调到最低以减少等待。
        # （标准端点不允许 thinking.disabled，用 reasoning_effort 两个端点都兼容。）
        extra_body={"reasoning_effort": "low"},
    )

    for chunk in stream:
        # 最后一个 usage chunk 可能没有 choices，跳过
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # 只打印正文 content；思维链在 delta.reasoning_content 里，这里不展示
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    print()  # 流结束后换行
    return 0


if __name__ == "__main__":
    sys.exit(main())
