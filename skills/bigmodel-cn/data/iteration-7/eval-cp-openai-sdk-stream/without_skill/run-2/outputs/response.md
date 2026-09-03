已写好 `main.py`，可直接 `python3 main.py` 运行（需先 `export GLM_CODING_PLAN_API_KEY=你的Key`）。

```python
#!/usr/bin/env python3
import os
import sys

from openai import OpenAI

# GLM Coding Plan 专用的 OpenAI 兼容端点（与普通 /api/paas/v4 不同）
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_CODING_PLAN_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗。只输出诗句本身，不要标题和解释。"},
        ],
        stream=True,
    )

    for chunk in stream:
        # 部分 chunk（例如最后带 usage 的 chunk）可能没有 choices，需要跳过
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    print()  # 结束后换行


if __name__ == "__main__":
    main()
```

要点说明：

- **端点**：GLM Coding Plan 用的是专用地址 `https://open.bigmodel.cn/api/coding/paas/v4`，不是普通 API 的 `/api/paas/v4`。如果你的 Key 是普通开放平台 Key 而非 Coding Plan Key，把 `BASE_URL` 改成 `https://open.bigmodel.cn/api/paas/v4` 即可。
- **流式输出**：`stream=True` 后返回可迭代对象，每个 chunk 的 `choices[0].delta.content` 是增量文本，`print(..., end="", flush=True)` 实现边收边打印；最后 `print()` 补一个换行。
- **健壮性**：对没有 `choices` 的 chunk（如带 usage 统计的收尾 chunk）做了跳过处理，避免 `IndexError`。
- 运行：

```bash
export GLM_CODING_PLAN_API_KEY="你的Key"
python3 main.py
```
