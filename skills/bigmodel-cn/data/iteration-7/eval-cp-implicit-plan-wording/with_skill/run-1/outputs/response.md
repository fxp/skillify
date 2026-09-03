你用的是 GLM Coding Plan（编程套餐）Key，它和开放平台按量付费的 Key 是**两套隔离的计费体系**，最关键的区别是 **Base URL 不同**：

- 标准 API：`https://open.bigmodel.cn/api/paas/v4`
- **编程套餐：`https://open.bigmodel.cn/api/coding/paas/v4`**（多了 `/coding`）

套餐 Key 打到标准端点会返回 `429` + 业务码 `1113 余额不足或无可用资源包,请充值`——这不是让你充值，是端点用错了。下面的 `main.py` 已经用对了套餐端点。

## main.py

```python
#!/usr/bin/env python3
import os
import sys

import requests

# Coding Plan 专用端点（不是 /api/paas/v4）
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
CHAT_COMPLETIONS_URL = f"{CODING_PLAN_BASE_URL}/chat/completions"

MODEL = "glm-5.3"
PROMPT = "用一句话介绍 Rust"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY（填 GLM Coding Plan 套餐的 Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        # glm-5.3 默认思考强度为 max；一句话的问题用 low 即可，更快、更省套餐额度
        "reasoning_effort": "low",
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(
            CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        print(f"请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code, msg = err.get("code"), err.get("message")
        print(f"API 返回 HTTP {resp.status_code}，业务码 {code}：{msg or resp.text}", file=sys.stderr)
        if str(code) == "1113":
            print(
                "提示：1113 通常不是真的余额不足。请确认：\n"
                "  1) ZHIPU_API_KEY 是 GLM Coding Plan 套餐 Key；\n"
                "  2) 请求打的是 …/api/coding/paas/v4，而不是 …/api/paas/v4；\n"
                "  3) 模型是 glm-5.3 或 glm-5.3-flash；\n"
                "  4) 以上都对，才可能是 5 小时/每周套餐额度用完，等窗口刷新即可。",
                file=sys.stderr,
            )
        return 1

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content") or ""
    if choice.get("finish_reason") not in (None, "stop", "length"):
        print(f"警告：finish_reason = {choice.get('finish_reason')}", file=sys.stderr)

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行

```bash
pip install requests
export ZHIPU_API_KEY="你的编程套餐 Key"   # 在 bigmodel.cn/coding-plan/personal/overview 里创建的那把
python3 main.py
```

## 几点说明

1. **Key 来源**：套餐 Key 在 `https://bigmodel.cn/coding-plan/personal/overview` 里新建，和控制台「项目管理 > API Keys」里的按量付费 Key 不通用。
2. **鉴权**：请求头 `Authorization: Bearer <KEY>`，请求体字段与标准 `chat/completions` 完全一致，只是 URL 多了 `/coding`。
3. **模型**：套餐内只有 `glm-5.3` 和 `glm-5.3-flash` 的对话能力；embeddings、生图、rerank 等不在套餐内，用套餐 Key 调会同样报 `1113`，需要另买标准 API。
4. **思考模式**：`glm-5.3` 默认深度思考强度为 `max`，我在请求里传了 `reasoning_effort: "low"`，一句话的问题更快也更省额度（Pro 版 5 小时 12,000 额度，按 输入×6.9 + 输出×24 / 10000 扣）。想要更强推理可改为 `"high"` 或 `"max"`。
5. **合规提醒**：官方条款写明套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode、Kilo Code 等）。自己写脚本调 Coding 端点技术上能跑通，但属于条款之外的用法，是否扣额度/是否被限制以官方为准；生产系统建议用标准 API Key 走 `…/api/paas/v4`。
