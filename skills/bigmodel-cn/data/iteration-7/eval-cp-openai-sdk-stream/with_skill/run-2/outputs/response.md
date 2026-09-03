已写好 `main.py`，用 OpenAI 官方 Python SDK 以流式方式调用 GLM Coding Plan 的 `glm-5.3-flash`，边收边打印，最后换行结束。

## 运行方式

```bash
pip install --upgrade 'openai>=1.0'   # 已安装可跳过
export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
python3 main.py
```

## main.py

```python
"""用 OpenAI 官方 SDK 以流式方式调用智谱 GLM Coding Plan 的 glm-5.3-flash。

运行前：
    export GLM_CODING_PLAN_API_KEY="你的 Coding Plan 套餐 Key"
    python3 main.py

注意：Coding Plan 套餐 Key 必须打 /api/coding/paas/v4 端点；
打标准端点 /api/paas/v4 会报 429 + 1113 "余额不足"，那不是要充值，而是 Base URL 用错了。
"""

import os
import sys

from openai import OpenAI

# Coding Plan 专用 Base URL（比标准 API 多了 /coding 这一级，末尾不要再拼 /v1）
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.3-flash"


def main() -> None:
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）")

    client = OpenAI(api_key=api_key, base_url=CODING_PLAN_BASE_URL)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": "请写一首关于秋天的四行小诗，只输出诗句本身。"},
        ],
        stream=True,
        temperature=0.8,
    )

    finish_reason = None
    for chunk in stream:
        # 最后一个带 usage 的 chunk 里 choices 可能为空，先做保护
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        # glm-5.3-flash 默认开启深度思考，delta 里可能先有 reasoning_content；
        # 这里只打印正文 content，忽略思维链。
        if delta.content:
            print(delta.content, end="", flush=True)
        if choice.finish_reason:
            finish_reason = choice.finish_reason

    # 收完后换行结束
    print()

    # 流式没有独立错误码，异常会体现在 finish_reason 里
    if finish_reason not in (None, "stop"):
        print(f"[提示] 生成非正常结束：finish_reason={finish_reason}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

## 几个关键点

1. **Base URL 必须是 Coding Plan 专用的** `https://open.bigmodel.cn/api/coding/paas/v4`，比标准 API 的 `…/api/paas/v4` 多了 `/coding` 一级。套餐 Key 打标准端点会直接报 `429` + `1113 余额不足或无可用资源包`——这不是让你充值，是 Base URL 用错了。另外 Coding 端点路径里没有 `/v1`，OpenAI SDK 自己不会追加，不要手动拼成 `…/v4/v1`（会 404）。
2. **Key 从 `GLM_CODING_PLAN_API_KEY` 读取**，没设置时直接退出并提示，不会硬编码。Coding Plan 的 Key 和开放平台按量付费的 Key 不通用。
3. **流式处理细节**：
   - `glm-5.3-flash` 默认开启深度思考，流里可能先推 `delta.reasoning_content`（思维链），脚本只打印 `delta.content` 正文，思维链不输出到终端。
   - 最后一个带 `usage` 的 chunk 可能 `choices` 为空，已做保护，避免 `IndexError`。
   - 流式没有独立错误码，异常体现在 `finish_reason`（如 `length`、`sensitive`、`network_error`），非 `stop` 时会在 stderr 给出提示。
   - `temperature` 合法区间是 `(0,1)`，这里用 0.8 让诗句更有变化；不要传 0。
4. **提醒**：按智谱官方条款，Coding Plan 套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode 等）。自己写脚本调 Coding 端点技术上能跑通，但属于条款之外的用法，是否消耗套餐额度、是否被限制以官方为准；生产系统建议用标准 API Key（Base URL 改回 `…/api/paas/v4`）。
