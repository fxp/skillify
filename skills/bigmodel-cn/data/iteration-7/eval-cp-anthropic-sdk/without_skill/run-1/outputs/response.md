# 用 anthropic 官方 SDK 调用 GLM Coding Plan 的 glm-5.3

智谱 GLM Coding Plan 提供了 **Anthropic 协议兼容端点**，所以不需要改用智谱自己的 SDK：直接用 `anthropic` 包，把 `base_url` 指到智谱、`model` 填 `glm-5.3` 即可，其余写法和调用 Claude 完全一样。

## main.py

```python
#!/usr/bin/env python3
import os
import sys

import anthropic

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/anthropic"  # Coding Plan 的 Anthropic 兼容端点（国内站）
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

    # 回复是 content block 列表；只拼接 text 块（GLM 可能返回 thinking 块，直接跳过）
    answer = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行

```bash
pip install -U anthropic            # 已安装可跳过
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
python3 main.py
```

预期输出类似：`1 到 10 之间的质数有：2、3、5、7。`

## 几点说明

- **Key 只走环境变量**：脚本不硬编码 Key，缺失时会给出明确提示并退出码 1。
- **base_url 是关键**：`https://open.bigmodel.cn/api/anthropic` 是智谱国内站的 Anthropic 兼容地址；如果你用的是海外站（z.ai）的 Coding Plan，改成 `https://api.z.ai/api/anthropic`，或直接 `export GLM_ANTHROPIC_BASE_URL=...` 覆盖，不用改代码。
- **不要设 `ANTHROPIC_API_KEY`**：显式传 `api_key=` 后 SDK 不会再读 `ANTHROPIC_API_KEY`，避免把真正的 Claude Key 误发给智谱。
- **文本提取**：`response.content` 是 block 列表，代码只拼接 `type == "text"` 的块，这样即使模型开启思考模式返回额外的 thinking 块也不会报错。
- **模型名**：按你的要求用 `glm-5.3`；如果接口返回“模型不存在”之类的 4xx 错误，请到智谱控制台确认你套餐里可用的模型标识（例如 `glm-5`、`glm-5.1` 等）并替换 `MODEL` 常量。
