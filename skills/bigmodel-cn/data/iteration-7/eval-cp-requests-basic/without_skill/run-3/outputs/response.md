已写好 `main.py`，用 `requests` 直接调用智谱 GLM Coding Plan 的 Chat Completions 接口，让 `glm-5.3` 用一句话介绍 Python，并把回答打印到 stdout。

## 使用方法

```bash
pip install requests
export GLM_KEY="你的智谱 API Key"
python3 main.py
```

## 脚本要点

- **接口地址**：GLM Coding Plan 套餐使用专属的 coding 端点 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（不是普通的 `/api/paas/v4/...`），套餐 Key 只能走这个端点。
- **鉴权**：请求头 `Authorization: Bearer $GLM_KEY`，Key 只从环境变量 `GLM_KEY` 读取，不写死在代码里；缺少环境变量时直接报错退出。
- **请求体**：OpenAI 兼容格式，`model` 为 `glm-5.3`，`messages` 里一条 user 消息「用一句话介绍 Python」，`stream: false`。
- **输出**：解析 `choices[0].message.content` 打印到 stdout；HTTP 非 200、网络异常或响应结构异常都会把错误信息写到 stderr 并以非 0 退出码结束，方便排查。

## main.py

```python
#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM Coding Plan 的 Chat Completions 接口，让 glm-5.3 用一句话介绍 Python。"""

import os
import sys

import requests

# GLM Coding Plan 套餐使用专属的 coding 端点（与普通 API 端点不同）
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（智谱 API Key）", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "用一句话介绍 Python"},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        print(f"请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"接口返回错误 HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        print(f"无法解析响应：{resp.text}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 备注

- 如果运行时返回 `401`/`403` 或提示模型不可用，请确认：Key 是 Coding Plan 套餐的 Key、端点是 `/api/coding/paas/v4`、以及套餐里 `glm-5.3` 的确切模型名（可在智谱开放平台的 Coding Plan 页面核对）。
- 脚本已通过 `python3 -m py_compile` 语法检查；实际请求需要有效的 `GLM_KEY` 才能跑通。
