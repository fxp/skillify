# GLM Coding Plan 套餐：用 requests 直接调用 glm-5.3

脚本已保存为 `main.py`，运行方式：

```bash
pip install requests
export GLM_KEY="你的 GLM Coding Plan 套餐 Key"
python3 main.py
```

## main.py

```python
#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）的 Key 直接通过 HTTP 调用 glm-5.3。

- 套餐 Key 必须打 Coding 端点 `https://open.bigmodel.cn/api/coding/paas/v4`，
  打标准端点 `…/api/paas/v4` 会报 HTTP 429 + 业务码 1113「余额不足」，这不是要充值。
- API Key 从环境变量 GLM_KEY 读取，不要硬编码。
- 运行：GLM_KEY=xxx python3 main.py
"""

import os
import sys

import requests

# 注意是 /api/coding/paas/v4，不是 /api/paas/v4；路径里也没有 /v1 这一级
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 套餐内可用模型：glm-5.3 / glm-5.3-flash


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（GLM Coding Plan 套餐的 API Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        "stream": False,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 智谱错误体格式：{"error": {"code": "1113", "message": "..."}}
        try:
            err = resp.json().get("error", {})
            code, msg = err.get("code"), err.get("message")
        except ValueError:
            code, msg = None, resp.text
        print(f"HTTP {resp.status_code}，业务错误码 {code}：{msg}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是真的余额不足。请确认 GLM_KEY 是 Coding Plan 套餐 Key，"
                "且模型是 glm-5.3 / glm-5.3-flash；套餐 Key 不能用于 embeddings/生图等套餐外能力。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    if finish_reason not in (None, "stop", "length"):
        print(f"警告：finish_reason = {finish_reason}", file=sys.stderr)

    content = choice["message"].get("content") or ""
    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 几个关键点（Coding Plan 和标准 API 不一样）

1. **Base URL 必须是 Coding 端点**：`https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`。套餐 Key 和开放平台按量付费的 Key 是两套隔离的计费体系，套餐 Key 打标准端点 `…/api/paas/v4` 会直接返回 HTTP 429 + `{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`——遇到这个错误不用充值，改 URL 即可。
2. **路径里没有 `/v1`**：`…/coding/paas/v4/v1/chat/completions` 会 404，脚本里已写成完整路径。
3. **鉴权是 `Authorization: Bearer <GLM_KEY>`**，Key 用套餐页面（`https://bigmodel.cn/coding-plan/personal/overview`）里创建的 Key，不是控制台的平台 Key。
4. **模型**：套餐内只有 `glm-5.3` 和 `glm-5.3-flash`；`glm-5.3` 在标准端点强制开启深度思考，本脚本没传 `thinking` 参数，走默认行为即可，回答在 `choices[0].message.content` 里（思维链在 `reasoning_content`，脚本不打印）。
5. **请求体和标准 API 完全一致**，只是换了 Base URL 和 Key；套餐不包含 embeddings / rerank / 生图等能力，这些要另用标准 Key 走 `…/api/paas/v4`。
6. **提醒**：官方条款规定 Coding Plan 套餐仅限在 Claude Code / OpenCode / Kilo Code 等指定工具环境中使用。自己写脚本直接打 Coding 端点在技术上能通，但属于条款之外的用法，是否消耗套餐额度、是否被限制以官方为准；生产系统建议使用标准 API Key。
