#!/usr/bin/env python3
"""
通过 anthropic 官方 SDK（Messages API）调用智谱 GLM Coding Plan 的 glm-5.3。

用法：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
    python3 main.py

可选：
    export GLM_ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"  # 默认值，国内站
    # 海外站（z.ai）可改为 https://api.z.ai/api/anthropic
"""

import os
import sys

import anthropic

# Coding Plan 提供 Anthropic 协议兼容端点，只需把 base_url 指到智谱即可，
# 其余用法与调用 Claude 完全一致。
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
MODEL = "glm-5.3"
QUESTION = "1 到 10 的质数有哪些"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print(
            "错误：未找到环境变量 GLM_CODING_PLAN_API_KEY。\n"
            '请先执行：export GLM_CODING_PLAN_API_KEY="你的 Key"',
            file=sys.stderr,
        )
        return 1

    base_url = os.environ.get("GLM_ANTHROPIC_BASE_URL", DEFAULT_BASE_URL)

    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": QUESTION}],
        )
    except anthropic.APIStatusError as exc:
        print(f"请求失败（HTTP {exc.status_code}）：{exc.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as exc:
        print(f"无法连接到 {base_url}：{exc}", file=sys.stderr)
        return 1

    # 回复是 content block 列表；只拼接 text 类型的块（GLM 可能带 thinking 块，直接跳过）。
    answer = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
