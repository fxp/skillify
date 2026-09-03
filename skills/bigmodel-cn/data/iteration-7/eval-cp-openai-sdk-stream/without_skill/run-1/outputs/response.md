已写好 `main.py`，直接 `python3 main.py` 即可运行（需先 `export GLM_CODING_PLAN_API_KEY=你的Key`）。

```python
#!/usr/bin/env python3
"""用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行前请设置环境变量：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan API Key"
然后直接：
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan 的 OpenAI 兼容端点（注意路径里的 /coding/）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        return 1

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "写一首关于秋天的四行小诗。"},
        ],
        stream=True,
    )

    for chunk in stream:
        # 部分 chunk（如末尾带 usage 的）可能没有 choices，跳过即可
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    # 流结束后换行收尾
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

几点说明：

- **Base URL**：GLM Coding Plan 的 OpenAI 兼容地址是 `https://open.bigmodel.cn/api/coding/paas/v4`，和普通开放平台的 `https://open.bigmodel.cn/api/paas/v4` 不同，Coding Plan 的 Key 只能走带 `/coding/` 的这个地址，否则会报鉴权/权限错误。
- **流式输出**：`stream=True` 后返回一个迭代器，逐个 `chunk` 取 `choices[0].delta.content` 并用 `print(..., end="", flush=True)` 即时打印；末尾 `print()` 换行结束。
- **健壮性**：跳过了没有 `choices` 的 chunk（有些兼容端点会在流末尾单独发一个只带 usage 的 chunk），并对 `content` 为 `None` 的 delta 做了判断。
- 未设置环境变量时会在 stderr 提示并以退出码 1 结束，不会抛出一堆栈信息。

运行：

```bash
export GLM_CODING_PLAN_API_KEY="你的Key"
python3 main.py
```
