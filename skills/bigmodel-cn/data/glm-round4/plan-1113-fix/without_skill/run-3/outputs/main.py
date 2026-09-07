"""问 GLM「用一句话介绍 Python」并把回答打印到 stdout。

原代码报 429 / 1113「余额不足或无可用资源包」的真正原因不是额度用完:

1. 端点用错了。GLM Coding Plan 的额度只能从套餐专用端点抵扣;
   https://open.bigmodel.cn/api/paas/v4/chat/completions 是标准计费端点,
   请求会走账号余额扣费,所以套餐再有额度也报 1113。
   Coding Plan 的 OpenAI 兼容端点是:
   https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
2. 取 Key 的写法错了。os.environ[chr(39) + chr(39)] 取的是名为 '' 的
   环境变量,应该读 GLM_KEY。
"""

import os
import sys

import requests

URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"


def main() -> None:
    api_key = os.environ.get("GLM_KEY")
    if not api_key:
        print("请先设置环境变量 GLM_KEY", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    print(resp.json()["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
