已写好 `main.py`，用 OpenAI 官方 Python SDK 流式调用 GLM Coding Plan 的 `glm-5.3-flash`：

```python
import os
import sys

from openai import OpenAI

BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）")

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "写一首关于秋天的四行小诗，只输出诗本身，不要标题和解释。"},
        ],
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:          # 末尾 usage chunk 可能没有 choices
            continue
        delta = chunk.choices[0].delta
        if delta.content:              # 只打印正文，忽略 reasoning_content 思维链
            print(delta.content, end="", flush=True)

    print()                            # 结束后换行


if __name__ == "__main__":
    main()
```

运行方式：

```bash
pip install --upgrade 'openai>=1.0'
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
python3 main.py
```

几个关键点（都是 Coding Plan 特有的坑）：

1. **Base URL 必须是 `https://open.bigmodel.cn/api/coding/paas/v4`**，比标准 API 多了一段 `/coding`。套餐 Key 打标准端点 `…/api/paas/v4` 会直接报 `429` + `1113 余额不足`，那不是让你充值，是 Base URL 填错了。
2. **Base URL 填到 `/v4` 为止**，不要自己再拼 `/v1`——OpenAI SDK 只会在后面追加 `/chat/completions`，Coding 端点没有 `/v1` 这一级（拼了会 404）。
3. **套餐 Key 和开放平台按量 Key 不通用**，所以脚本单独用 `GLM_CODING_PLAN_API_KEY` 这个变量名，别和 `ZHIPUAI_API_KEY` 混用。
4. `glm-5.3-flash` 默认开启深度思考，流式 `delta` 里可能先出现 `reasoning_content`（思维链），再出现 `content`（正文）。脚本只打印 `content`，所以开头会有一小段“空白等待”是正常的。
5. 流最后一个 chunk 可能只带 `usage`、`choices` 为空，所以循环里先判空再取 `delta`，避免 `IndexError`。

另外提醒一下：官方条款写明 Coding Plan 套餐“仅限在官方支持的指定工具与产品环境中使用”（Claude Code、OpenCode 等），自己写脚本直连 Coding 端点技术上能通，但属于条款之外的用法；如果是生产系统，建议改用开放平台按量付费的标准 Key + `…/api/paas/v4`，代码只需换这两个构造参数。
