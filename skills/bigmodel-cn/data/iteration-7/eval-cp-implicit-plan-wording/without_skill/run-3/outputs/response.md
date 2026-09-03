已写好 `main.py`，直接 `python3 main.py` 即可运行（需先 `pip install requests`，并 `export ZHIPU_API_KEY=你的key`）。

几点说明：

1. **端点**：你用的是 GLM 编程套餐（Coding Plan，包月、按 5 小时额度计），这类 Key 走的是专用端点
   `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`，
   而不是按量付费的通用端点 `/api/paas/v4/...`。走通用端点会报无权限/余额不足之类的错误。脚本里已经用了 coding 端点。
2. **协议**：OpenAI 兼容格式，`Authorization: Bearer <key>`，`model` 填 `glm-5.3`，非流式（`stream: false`），从 `choices[0].message.content` 取回答并打印。
3. **错误处理**：未设置 `ZHIPU_API_KEY`、网络异常、非 200 状态码、响应结构异常时会打印到 stderr 并以非 0 退出。

```python
#!/usr/bin/env python3
import os
import sys

import requests

CODING_PLAN_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 ZHIPU_API_KEY", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 Rust"}],
        "stream": False,
    }

    try:
        resp = requests.post(CODING_PLAN_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}：{resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"响应格式异常：{data}", file=sys.stderr)
        return 1

    print(content.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

如果你的套餐是在海外站（z.ai）开通的，把 URL 换成 `https://api.z.ai/api/coding/paas/v4/chat/completions` 即可。
