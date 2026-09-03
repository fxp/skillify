#!/usr/bin/env python3
"""通过 anthropic 官方 SDK（Messages API）调用智谱 GLM Coding Plan 的 glm-5.3。

用法:
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
    python3 main.py
"""

import os
import sys

import anthropic

# 智谱 GLM Coding Plan 的 Anthropic 兼容端点
BASE_URL = "https://open.bigmodel.cn/api/anthropic"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key, base_url=BASE_URL)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "1 到 10 的质数有哪些"}],
        )
    except anthropic.APIStatusError as e:
        print(f"请求失败（HTTP {e.status_code}）：{e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as e:
        print(f"连接失败：{e}", file=sys.stderr)
        return 1

    # 只拼接 text 块，忽略 thinking 等非文本块
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
