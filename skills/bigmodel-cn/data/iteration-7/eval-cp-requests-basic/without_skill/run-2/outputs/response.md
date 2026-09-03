已为你写好 `main.py`，用标准库 + `requests` 直接调用智谱 GLM Coding Plan 的 HTTP 接口，让 `glm-5.3` 回答“用一句话介绍 Python”，并把回答打印到 stdout。

## 使用方法

```bash
pip install requests          # 如尚未安装
export GLM_KEY="你的 API Key"
python3 main.py
```

## 脚本说明

- **接口地址**：GLM Coding Plan 套餐使用专用端点 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`（与普通按量计费的 `/api/paas/v4` 不同，Coding Plan 的 Key 需走 coding 端点）。如需切换端点，可设置环境变量 `GLM_BASE_URL`。
- **鉴权**：请求头 `Authorization: Bearer $GLM_KEY`。
- **请求体**：OpenAI 兼容格式，`model` 为 `glm-5.3`，`messages` 中一条 user 消息 `用一句话介绍 Python`，`stream: false`。
- **输出**：解析 `choices[0].message.content` 后打印到 stdout；未设置 `GLM_KEY`、网络错误、非 200 状态码或响应格式异常时，错误信息输出到 stderr 并以非零退出码结束。
- 模型名可通过 `GLM_MODEL` 环境变量覆盖（默认 `glm-5.3`）。

```python
#!/usr/bin/env python3
"""用 requests 直接调用智谱 GLM Coding Plan 的 HTTP 接口，让 glm-5.3 一句话介绍 Python。"""

import os
import sys

import requests

BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
MODEL = os.environ.get("GLM_MODEL", "glm-5.3")


def main() -> int:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY，请先 export GLM_KEY=你的APIKey", file=sys.stderr)
        return 1

    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        "stream": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"错误：请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"错误：HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        return 1

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        print(f"错误：无法解析响应：{resp.text}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 备注

- 我这里没有你的 Key，无法实际发起请求，脚本已通过 `python3 -m py_compile` 语法检查。
- 如果运行时返回 401/1xxx 类错误，请确认：① Key 是 Coding Plan 套餐的 Key；② 端点是 `/api/coding/paas/v4`；③ 模型名 `glm-5.3` 在你的套餐中可用（不可用时可改 `GLM_MODEL`）。
