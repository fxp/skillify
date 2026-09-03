脚本已写好：`main.py`。核心要点先说清楚，因为这是 Coding Plan 最容易踩坑的地方：

## 关键：Coding Plan 的端点和标准 API 不一样

| | 标准 API（按量付费 Key） | GLM Coding Plan（你买的套餐 Key） |
| :-- | :-- | :-- |
| Base URL | `https://open.bigmodel.cn/api/paas/v4` | `https://open.bigmodel.cn/api/coding/paas/v4`（多了 `/coding`） |
| 可用模型 | 全部 | `glm-5.3`、`glm-5.3-flash` |

- 用套餐 Key 打标准端点会报 **HTTP 429 + `{"error":{"code":"1113","message":"余额不足或无可用资源包,请充值。"}}`**——这不是要你充值，是 Base URL 错了。
- 路径是 `.../coding/paas/v4/chat/completions`，`v4` 后面**没有** `/v1` 这一级（拼成 `/v4/v1/...` 会 404）。
- 鉴权就是普通的 `Authorization: Bearer <GLM_KEY>`，请求体和标准 chat/completions 完全一致。

## main.py

```python
#!/usr/bin/env python3
import os
import sys

import requests

URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY（请填入 GLM Coding Plan 的 API Key）", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        "stream": False,
        "max_tokens": 1024,  # glm-5.3 默认开思考，思考 token 也占输出额度，别设太小
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(URL, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content")
    if not content:
        print(f"模型未返回文本，finish_reason={choice.get('finish_reason')}，原始响应：{data}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行

```bash
pip install requests
export GLM_KEY="你的 Coding Plan Key"   # 在 https://bigmodel.cn/coding-plan/personal/overview 创建
python3 main.py
```

正常会在 stdout 打印一句话（例如"Python 是一种简洁易读、生态丰富的通用高级编程语言……"）。响应里可能还有 `reasoning_content`（思维链），脚本只打印 `message.content`。

## 排错

- **429 + code 1113**：先检查 URL 是不是 `/api/coding/paas/v4`，再检查 `GLM_KEY` 是不是套餐 Key（不是开放平台 API Key），再确认模型是 `glm-5.3`/`glm-5.3-flash`。只有这三项都对了，1113 才可能真的是 5 小时/每周额度用完，等窗口刷新即可。
- **404**：路径多拼了 `/v1`。
- 套餐**不含** embeddings、生图、rerank 等能力，那些需要另买标准 API 资源包并换用 `.../api/paas/v4`。

一点提醒：官方条款写明套餐"仅限在官方支持的指定工具与产品环境中使用"（Claude Code、OpenCode 等）。自己写脚本直接调 Coding 端点技术上能跑通，但属于条款外用法，生产系统建议用标准 API Key。
