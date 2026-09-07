"""向智谱 GLM 提问"用一句话介绍 Python"，并把回答打印到 stdout。

报 1113（余额不足或无可用资源包）的原因：
GLM Coding Plan（Max）的套餐额度只在 Coding 专用端点上生效，
原代码用的 https://open.bigmodel.cn/api/paas/v4 是按量付费端点，
不走套餐额度，所以提示"余额不足"。
改用 OpenAI 兼容的 Coding 端点即可：
https://open.bigmodel.cn/api/coding/paas/v4
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
MODEL = "glm-5.3"


def main() -> int:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 GLM_KEY（智谱 API Key）", file=sys.stderr)
        return 1

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        # 出错时把状态码和响应体打到 stderr，方便排查（如 1113 余额问题）
        print(f"HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    answer = data["choices"][0]["message"]["content"]
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
