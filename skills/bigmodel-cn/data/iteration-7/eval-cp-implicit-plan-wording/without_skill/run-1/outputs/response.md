已写好 `main.py`，直接 `python3 main.py` 即可运行（前提：已 `pip install requests`，并 `export ZHIPU_API_KEY=你的key`）。

## 关键点：编程套餐要走专用网关

你买的是 GLM 编程套餐（Coding Plan，按 5 小时额度的包月），它的 Key **不能**走按量付费的通用接口 `https://open.bigmodel.cn/api/paas/v4`，否则会报鉴权/余额类错误。要用编程套餐专用的 OpenAI 兼容网关（路径里多一段 `/coding/`）：

```
https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
```

请求格式与 OpenAI Chat Completions 一致：`Authorization: Bearer <key>`，body 里给 `model` 和 `messages`。

## main.py

```python
#!/usr/bin/env python3
import os
import sys

import requests

# 编程套餐专用的 OpenAI 兼容网关（注意路径里的 /coding/）
BASE_URL = os.environ.get("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
MODEL = os.environ.get("ZHIPU_MODEL", "glm-5.3")


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY", file=sys.stderr)
        return 1

    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Rust"}],
        # 关闭思考模式，直接拿到简短回答
        "thinking": {"type": "disabled"},
        "stream": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        print(f"请求失败：{e}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应格式异常：{data}", file=sys.stderr)
        return 1

    print(answer.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 运行

```bash
pip install requests
export ZHIPU_API_KEY="你的编程套餐 Key"
python3 main.py
```

## 说明

- `thinking: {"type": "disabled"}`：GLM 新模型默认可能开启思考模式，关掉后回复更短、更快；如果你想看推理过程，把这一行删掉即可。
- 非 200 或响应结构异常时会把原始返回打到 stderr，方便排查（比如套餐额度用完、模型名不在套餐范围内等）。
- 如果以后想切回按量付费的 Key，只需 `export ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4`，代码不用改。
