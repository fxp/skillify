"""用 anthropic 官方 SDK（Messages API）通过 GLM Coding Plan 调用 glm-5.3。

运行方式：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py

要点（来自智谱官方 Coding Plan 文档）：
- Anthropic 兼容端点是 https://open.bigmodel.cn/api/anthropic
  （标准 API 与 Coding Plan 共用这个端点，走哪套额度由 Key 决定；
   SDK 会自动拼上 /v1/messages）。
- Key 必须是 Coding Plan 套餐 Key，不是开放平台按量 Key；
  套餐只包含 glm-5.3 / glm-5.3-flash 两个对话模型。
"""

import os
import sys

import anthropic

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
        # 常见错误：套餐 Key 打错端点 / 额度用尽会返回 429 + 1113
        sys.exit(f"请求失败 HTTP {e.status_code}: {e.message}")

    # glm-5.3 默认开启深度思考，响应里可能夹带 thinking 块，只打印文本块
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )
    print(text)


if __name__ == "__main__":
    main()
