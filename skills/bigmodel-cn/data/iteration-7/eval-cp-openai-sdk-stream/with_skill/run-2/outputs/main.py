"""用 OpenAI 官方 SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行前：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py

注意：Coding Plan 套餐 Key 必须打 /api/coding/paas/v4 端点；
打标准端点 /api/paas/v4 会报 429 + 1113 "余额不足"，那不是要充值，而是 Base URL 用错了。
"""

import os
import sys

from openai import OpenAI

# Coding Plan 专用 Base URL（比标准 API 多了 /coding 这一级，末尾不要再拼 /v1）
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）")

    client = OpenAI(api_key=api_key, base_url=CODING_PLAN_BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗，只输出诗句本身。"},
        ],
        stream=True,
        temperature=0.8,
    )

    finish_reason = None
    for chunk in stream:
        # 最后一个带 usage 的 chunk 里 choices 可能为空，先做保护
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        # glm-5.3-flash 默认开启深度思考，delta 里可能先有 reasoning_content；
        # 这里只打印正文 content，忽略思维链。
        if delta.content:
            print(delta.content, end="", flush=True)
        if choice.finish_reason:
            finish_reason = choice.finish_reason

    # 收完后换行结束
    print()

    # 流式没有独立错误码，异常会体现在 finish_reason 里
    if finish_reason not in (None, "stop"):
        print(f"[提示] 生成非正常结束：finish_reason={finish_reason}", file=sys.stderr)


if __name__ == "__main__":
    main()
