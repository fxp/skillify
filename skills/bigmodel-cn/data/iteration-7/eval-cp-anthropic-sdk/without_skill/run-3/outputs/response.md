# 用 anthropic SDK 调用 GLM Coding Plan 的 glm-5.3

智谱 GLM Coding Plan 提供了 Anthropic Messages API 兼容端点，所以可以直接用 `anthropic` 官方 SDK，只需把 `base_url` 指向智谱的兼容地址、`api_key` 换成 Coding Plan 的 Key 即可（和 Claude Code 接入时配置 `ANTHROPIC_BASE_URL` 是同一个地址）。

## main.py

```python
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
```

## 运行

```bash
pip install anthropic          # 已安装可跳过
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan Key"
python3 main.py
```

预期输出类似：

```
1 到 10 之间的质数有：2、3、5、7。
```

## 几点说明

- **base_url**：`https://open.bigmodel.cn/api/anthropic`。SDK 会在其后拼接 `/v1/messages`，不要自己再加 `/v1`。海外站（z.ai）用户对应的是 `https://api.z.ai/api/anthropic`，可通过环境变量 `GLM_ANTHROPIC_BASE_URL` 覆盖。
- **api_key**：Coding Plan 的 Key 直接传给 `anthropic.Anthropic(api_key=...)`，SDK 会放在 `x-api-key` 头里，智谱端点按此鉴权。不要同时设置 `ANTHROPIC_API_KEY` 环境变量以免混淆（脚本里显式传了 `api_key`，所以即使设置了也不受影响）。
- **model**：直接写 `glm-5.3`；若你的套餐里模型名不同（如 `glm-4.7` 等），改 `GLM_MODEL` 环境变量即可。
- **取文本**：兼容端点返回的 `content` 是标准的内容块列表，脚本只拼接 `type == "text"` 的块，避免开启思考模式时把 `thinking` 块混进输出。
- **错误处理**：Key 缺失、鉴权失败（401）、其他 API 错误都会打印到 stderr 并以非 0 退出，方便排查。
- 如需流式输出，把 `client.messages.create(...)` 换成 `with client.messages.stream(...) as stream: for t in stream.text_stream: print(t, end="", flush=True)` 即可，其余不变。
