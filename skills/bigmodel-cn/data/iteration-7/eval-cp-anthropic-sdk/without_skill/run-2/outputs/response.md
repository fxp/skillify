# 用 anthropic 官方 SDK 调用智谱 GLM Coding Plan 的 glm-5.3

智谱 GLM Coding Plan 提供了 Anthropic Messages API 兼容端点，因此可以直接用 `anthropic` 官方 SDK，只需把 `base_url` 指向智谱的兼容地址、`api_key` 换成你的 Coding Plan Key 即可。

## main.py

```python
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
```

## 运行方式

```bash
pip install anthropic          # 若尚未安装
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
python3 main.py
```

预期输出类似：

```
1 到 10 的质数有：2、3、5、7。
```

## 几点说明

- **端点**：Coding Plan 的 Anthropic 兼容地址是 `https://open.bigmodel.cn/api/anthropic`（SDK 会自动拼接 `/v1/messages`），不要写成普通的 `https://open.bigmodel.cn/api/paas/v4`，那是 OpenAI 兼容格式的地址。如果你用的是国际站（z.ai），把 base_url 换成 `https://api.z.ai/api/anthropic`。
- **Key**：脚本只从 `GLM_CODING_PLAN_API_KEY` 读取，通过 `api_key=` 显式传入，避免 SDK 去读默认的 `ANTHROPIC_API_KEY`。
- **取文本**：GLM 系列模型可能在 `content` 里返回 `thinking` 块，所以脚本只拼接 `type == "text"` 的块，而不是直接取 `message.content[0].text`，否则可能拿到思考内容或报错。
- **模型名**：`glm-5.3` 需要你的 Coding Plan 套餐支持；若返回模型不存在的错误，换成套餐内可用的型号（如 `glm-4.7` / `glm-5`）即可，其余代码不用改。
- **错误处理**：Key 缺失、HTTP 错误（401 鉴权失败、429 限流等）和网络连接失败都会打印到 stderr 并以非零退出码结束，方便排查。
