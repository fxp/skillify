"""用 anthropic 官方 SDK（Messages API）调用智谱 GLM Coding Plan 的 glm-5.3。

运行前：
    pip install anthropic
    export GLM_CODING_PLAN_API_KEY=<你的 Coding Plan 套餐 Key>
    python3 main.py
"""
import os
import sys

import anthropic

# Coding Plan 与标准 API 共用同一个 Anthropic 兼容端点，走哪套额度由 Key 决定。
BASE_URL = "https://open.bigmodel.cn/api/anthropic"
MODEL = "glm-5.3"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）")

    client = anthropic.Anthropic(api_key=api_key, base_url=BASE_URL)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "1 到 10 的质数有哪些"}],
        )
    except anthropic.APIStatusError as e:
        # 典型错误：用了平台按量 Key、或套餐额度耗尽，会返回 429 / 1113
        sys.exit(f"请求失败 HTTP {e.status_code}: {e.message}")

    # glm-5.3 强制开启思考，响应里可能夹带 thinking 块，只取 text 块打印
    text = "".join(block.text for block in message.content if block.type == "text")
    print(text)


if __name__ == "__main__":
    main()
