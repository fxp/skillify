# 用 anthropic SDK 调用 GLM Coding Plan 的 glm-5.3

## main.py

```python
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
```

## 运行

```bash
pip install anthropic
export GLM_CODING_PLAN_API_KEY=你的套餐Key
python3 main.py
```

## 几个关键点

1. **Base URL 是 `https://open.bigmodel.cn/api/anthropic`**。Anthropic 兼容层是标准 API 和 Coding Plan 共用的同一个端点，走套餐额度还是按量计费完全由 Key 决定；SDK 会自动在后面拼 `/v1/messages`，不要自己再加 `/v1`。
2. **Key 必须是 Coding Plan 套餐 Key**（在 `https://bigmodel.cn/coding-plan/personal/overview` 新建；团队版在「团队编程套餐 > 我的套餐」），和开放平台按量付费的 Key 不通用。如果报 `429` + `1113 余额不足`，通常是拿错了 Key（或套餐 5 小时/7 天额度用完了），不是要充值。
3. **模型只用 `glm-5.3` 或 `glm-5.3-flash`**，这是套餐官方保证可用的两个；其它旧模型名会被自动路由或直接报 1113，别依赖。
4. **只打印 `text` 块**：glm-5.3 强制开启思考，响应 `content` 里可能带 `thinking` 块，所以脚本按 `block.type == "text"` 过滤后再打印，而不是直接取 `content[0].text`。
5. **合规提醒**：官方条款写明套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本调这个端点技术上能通、也走套餐额度，但属于条款之外的用法；生产系统建议改用开放平台的标准 API Key。
