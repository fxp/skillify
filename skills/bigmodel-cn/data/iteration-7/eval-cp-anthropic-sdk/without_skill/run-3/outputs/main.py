#!/usr/bin/env python3
"""通过 anthropic 官方 SDK（Messages API）调用智谱 GLM Coding Plan 的 glm-5.3。

用法：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan Key"
    python3 main.py
"""

import os
import sys

import anthropic

# GLM Coding Plan 提供的 Anthropic 兼容端点（与 Claude Code 接入时的 ANTHROPIC_BASE_URL 相同）
BASE_URL = os.environ.get("GLM_ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        print('请先执行：export GLM_CODING_PLAN_API_KEY="你的 Key"', file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key, base_url=BASE_URL)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "1 到 10 的质数有哪些"}],
        )
    except anthropic.AuthenticationError as e:
        print(f"鉴权失败，请检查 GLM_CODING_PLAN_API_KEY 是否正确：{e}", file=sys.stderr)
        return 1
    except anthropic.APIError as e:
        print(f"调用失败：{e}", file=sys.stderr)
        return 1

    # 只拼接 text 块，忽略可能出现的 thinking 等其他类型的内容块
    text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
