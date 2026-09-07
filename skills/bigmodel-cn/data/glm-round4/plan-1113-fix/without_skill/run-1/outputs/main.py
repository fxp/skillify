"""调用智谱 GLM 并把回答打印到 stdout。

原代码报 429 / 1113「余额不足或无可用资源包」的根因：
1. 端点用错。https://open.bigmodel.cn/api/paas/v4/chat/completions 是按量计费的
   通用端点，GLM Coding Plan 套餐额度不在该端点抵扣，账户没有余额就会报 1113。
   Coding Plan 覆盖的 OpenAI Chat Completion 协议专用端点是
   https://open.bigmodel.cn/api/coding/paas/v4（Anthropic 协议则是 /api/anthropic）。
2. 取 Key 写错。os.environ[chr(39)+chr(39)] 读的是名为 '' 的环境变量，
   根本没取到 GLM_KEY。

用法：export GLM_KEY=你的APIKey && python3 main.py
"""

import os
import sys

import requests

# GLM Coding Plan 的 OpenAI Chat Completion 协议端点（套餐额度在此抵扣）
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
# 官方 FAQ：所有 Coding Plan 套餐均支持 GLM-5.3 与 GLM-5.3-Flash
MODEL = "glm-5.3"


def main() -> None:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY，例如：export GLM_KEY=你的APIKey")

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        # 打印状态码与响应体，便于排查（例如仍报 1113 时可直接看到服务端原因）
        sys.exit(f"请求失败：HTTP {resp.status_code} {resp.text}")

    answer = resp.json()["choices"][0]["message"]["content"]
    print(answer)


if __name__ == "__main__":
    main()
