已写好 `main.py`，用 anthropic 官方 SDK 走智谱的 Anthropic 兼容端点调用 `glm-5.3`，Key 从 `GLM_CODING_PLAN_API_KEY` 读取。

## main.py

```python
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
```

## 运行

```bash
pip install anthropic
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
python3 main.py
```

## 几个关键点

1. **Base URL 是 `https://open.bigmodel.cn/api/anthropic`**，标准 API 与 Coding Plan 共用这个 Anthropic 兼容端点，走套餐额度还是按量计费完全由 Key 决定。SDK 会自动拼上 `/v1/messages`，不要自己再加 `/v1`。
2. **Key 必须是套餐 Key**（在 `https://bigmodel.cn/coding-plan/personal/overview` 新建），不是开放平台按量付费的 Key，两者不通用。
3. **模型用 `glm-5.3`**（或更便宜的 `glm-5.3-flash`），这两个是套餐内明确支持的模型；请求 `glm-4.x` 等旧代码会被自动路由，不建议依赖。
4. **回答文本只取 `type == "text"` 的块**：GLM 在这条链路上可能返回 thinking 块，直接 `message.content[0].text` 有概率拿到思考内容或报错，所以脚本里做了过滤。
5. **看到 HTTP 429 + 错误码 `1113`（"余额不足"）不要去充值**：这几乎总是 Key/端点不匹配或模型、能力不在套餐内，脚本会在 stderr 里给出提示。

## 一个提醒

智谱官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本走 `/api/anthropic` 技术上已实测能通并消耗套餐额度，但属于条款之外的用法，是否会被限制以官方为准；如果是生产系统，建议用开放平台的标准 API Key。
