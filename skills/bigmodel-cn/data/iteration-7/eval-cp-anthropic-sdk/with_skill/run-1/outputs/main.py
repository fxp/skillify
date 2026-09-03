"""用 anthropic 官方 SDK（Messages API）通过 GLM Coding Plan 套餐调用 glm-5.3。

运行前：
    pip install anthropic
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py
"""

import os
import sys

import anthropic

# Coding Plan 与标准 API 共用这一个 Anthropic 兼容端点，走哪套额度由 Key 决定。
# 注意：不要写成 .../api/paas/v4（那是 OpenAI 兼容端点），SDK 会自己拼 /v1/messages。
BASE_URL = "https://open.bigmodel.cn/api/anthropic"
MODEL = "glm-5.3"  # 套餐内可用：glm-5.3 / glm-5.3-flash


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）。", file=sys.stderr)
        print("请先执行：export GLM_CODING_PLAN_API_KEY=\"你的套餐 Key\"", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key, base_url=BASE_URL)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "1 到 10 的质数有哪些"}],
        )
    except anthropic.APIStatusError as err:
        print(f"API 请求失败：HTTP {err.status_code} - {err.message}", file=sys.stderr)
        if "1113" in str(err):
            print(
                "提示：错误码 1113 通常不是真的余额不足，而是 Key 与端点不匹配"
                "（套餐 Key 只能走 /api/anthropic 或 /api/coding/paas/v4），"
                "或所请求的模型/能力不在套餐内。",
                file=sys.stderr,
            )
        return 1
    except anthropic.APIConnectionError as err:
        print(f"网络连接失败：{err}", file=sys.stderr)
        return 1

    # GLM 在 Coding 端点可能返回 thinking 块，这里只取 text 块，避免直接用 content[0] 取到思考内容。
    answer = "".join(block.text for block in message.content if block.type == "text")
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
