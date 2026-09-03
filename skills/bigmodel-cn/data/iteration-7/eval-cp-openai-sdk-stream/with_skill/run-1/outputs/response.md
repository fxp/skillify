# 用 OpenAI SDK 流式调用 GLM Coding Plan 的 glm-5.3-flash

脚本已保存为 `main.py`，直接 `python3 main.py` 即可运行。

## 关键点（Coding Plan 与标准 API 不同）

| 项目 | 取值 |
| :--- | :--- |
| Base URL | `https://open.bigmodel.cn/api/coding/paas/v4`（注意多了 `/coding`；不要在后面再拼 `/v1`，否则 404） |
| API Key | 环境变量 `GLM_CODING_PLAN_API_KEY`（套餐 Key，与开放平台按量 Key 不通用） |
| 模型 | `glm-5.3-flash`（套餐所有档位均支持） |

用套餐 Key 打标准端点 `…/api/paas/v4` 会报 HTTP 429 + `1113 余额不足`，这不是要充值，改 Base URL 即可。

## main.py

```python
"""用 OpenAI 官方 SDK 以流式方式调用智谱 GLM Coding Plan（glm-5.3-flash）写一首秋天小诗。

运行：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py
"""

import os
import sys

from openai import OpenAI

# GLM Coding Plan（编程套餐）专用 Base URL：比标准 API 多了 /coding 这一级。
# 套餐 Key 打标准端点 https://open.bigmodel.cn/api/paas/v4 会报 1113「余额不足」，不是要充值。
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> int:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print(
            "错误：未设置环境变量 GLM_CODING_PLAN_API_KEY。\n"
            "请先执行：export GLM_CODING_PLAN_API_KEY='你的 GLM Coding Plan 套餐 Key'",
            file=sys.stderr,
        )
        return 1

    client = OpenAI(api_key=api_key, base_url=CODING_PLAN_BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗，只输出诗句本身，不要标题和解释。"},
        ],
        stream=True,
        temperature=0.8,
        # glm-5.3-flash 默认强制开启深度思考，写小诗用不上，把推理强度调到最低以减少等待。
        # （标准端点不允许 thinking.disabled，用 reasoning_effort 两个端点都兼容。）
        extra_body={"reasoning_effort": "low"},
    )

    for chunk in stream:
        # 最后一个 usage chunk 可能没有 choices，跳过
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        # 只打印正文 content；思维链在 delta.reasoning_content 里，这里不展示
        if delta and delta.content:
            print(delta.content, end="", flush=True)

    print()  # 流结束后换行
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行

```bash
pip install --upgrade 'openai>=1.0'   # 已安装可跳过
export GLM_CODING_PLAN_API_KEY='你的套餐 Key'
python3 main.py
```

诗句会一个字一个字实时打印，流结束后自动换行退出。

## 几点说明

- **流式消费**：`stream=True` 后 SDK 会把 SSE 解析成 chunk 迭代器，增量文本在 `chunk.choices[0].delta.content`；结尾的 usage chunk 可能没有 `choices`，代码里已做判空。
- **深度思考**：`glm-5.3-flash` 默认强制思考，思维链走 `delta.reasoning_content`，脚本只打印正文。为减少等待，通过 `extra_body` 传了 `reasoning_effort: "low"`（该模型仅接受 `low` / `high` / `max`）；不想调节可直接删掉这一行。
- **temperature 区间**是 `(0, 1)`，不要传 0。
- **不要把 Key 写进代码**，脚本在缺少环境变量时会给出明确提示并退出。
- 官方条款规定 Coding Plan 套餐"仅限在官方支持的指定工具环境中使用"，自己写脚本调 Coding 端点技术上能通，但属条款之外用法，是否扣套餐额度以官方为准；生产系统请用标准 API Key（Base URL 改回 `…/api/paas/v4`）。
