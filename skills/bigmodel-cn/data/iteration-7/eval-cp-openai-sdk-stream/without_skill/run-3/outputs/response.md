已写好 `main.py`，用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 `glm-5.3-flash`，让它写一首关于秋天的四行小诗，边收边打印，最后换行结束。

## main.py

```python
#!/usr/bin/env python3
"""用 OpenAI 官方 Python SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行方式:
    export GLM_CODING_PLAN_API_KEY="你的 key"
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan 专用的 OpenAI 兼容端点（与普通按量计费端点不同）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print(
            "错误：未找到环境变量 GLM_CODING_PLAN_API_KEY，请先设置后再运行。",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "请写一首关于秋天的四行小诗，只输出诗句本身。",
            }
        ],
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            print(content, end="", flush=True)

    print()  # 结束换行
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行方式

```bash
pip install openai        # 如未安装
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan Key"
python3 main.py
```

## 几点说明

- **base_url**：GLM Coding Plan 走的是专用端点 `https://open.bigmodel.cn/api/coding/paas/v4`，和普通按量计费的 `https://open.bigmodel.cn/api/paas/v4` 不同。如果请求返回鉴权 / 套餐相关错误，请到智谱开放平台的 Coding Plan 页面核对当前给出的端点地址。
- **流式处理**：`stream=True` 后 `create()` 返回一个迭代器，每个 chunk 取 `choices[0].delta.content` 增量打印；`flush=True` 保证逐字实时输出。部分 chunk（如最后携带 `usage` 的那条）`choices` 可能为空，所以做了跳过处理。
- **Key 读取**：只从环境变量 `GLM_CODING_PLAN_API_KEY` 读取，未设置时给出明确提示并以非 0 退出。
- 脚本已通过 `python3 -m py_compile` 语法检查；实际请求需要有效 Key 和网络。
