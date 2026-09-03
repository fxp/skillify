# 用 anthropic SDK 通过 GLM Coding Plan 调用 glm-5.3

脚本已写好：`main.py`（已通过 `python3 -m py_compile` 语法检查）。

## 运行

```bash
pip install anthropic          # 如未安装
export GLM_CODING_PLAN_API_KEY=你的套餐Key
python3 main.py
```

## main.py

```python
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
        sys.exit(f"请求失败 HTTP {e.status_code}: {e.message}")

    # glm-5.3 默认开启深度思考，响应里可能夹带 thinking 块，只打印文本块
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )
    print(text)


if __name__ == "__main__":
    main()
```

## 几个关键点

1. **Base URL 是 `https://open.bigmodel.cn/api/anthropic`**，不是 OpenAI 兼容用的 `…/api/coding/paas/v4`。这是智谱的 Anthropic 兼容端点，标准 API 与 Coding Plan 共用同一个地址，走哪套额度由 Key 决定。SDK 会自动拼上 `/v1/messages`，不要自己再加 `/v1`。
2. **Key 必须是 Coding Plan 套餐 Key**（在 `https://bigmodel.cn/coding-plan/personal/overview` 新建），和开放平台按量付费的 Key 不通用。如果看到 `429` + 错误码 `1113 余额不足`，通常是拿套餐 Key 打了标准端点，或者调用了套餐不含的模型/能力，**不是要充值**。
3. **模型只用 `glm-5.3` 或 `glm-5.3-flash`**，套餐只含这两个对话模型。
4. `glm-5.3` 默认开启深度思考，返回的 `content` 里可能有 `thinking` 块，所以脚本只拼接 `type == "text"` 的块，避免把思考过程一起打印出来。
5. 脚本默认非流式，`max_tokens=1024` 对这个问题足够。

## 提醒

官方条款写明 Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode 等）。自己写脚本走 Anthropic 兼容端点在技术上能跑通（已有实测），但属于条款之外的用法；如果是生产用途，建议换成开放平台标准 API Key。
