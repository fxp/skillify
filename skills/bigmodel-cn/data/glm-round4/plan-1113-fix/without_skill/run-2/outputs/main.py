"""调用智谱 GLM Coding Plan 的 OpenAI 兼容接口，问一个问题并打印回答。

原代码报 429 / 1113（余额不足或无可用资源包）的原因：
1. Coding Plan 套餐额度只在专属 coding 端点生效（Base URL 为
   https://open.bigmodel.cn/api/coding/paas/v4）。原代码用的
   /api/paas/v4/chat/completions 是标准按量计费端点，不消耗套餐额度，
   账户没有按量余额就会报 1113。
2. 原代码取 Key 的写法 os.environ[chr(39)+chr(39)] 实际读取的是名为
   '' 的环境变量，本身就是错的，这里改为读取 GLM_KEY。

用法：export GLM_KEY=你的Key && python3 main.py
"""

import os
import sys

import requests

# Coding Plan 专属端点（OpenAI 兼容），完整 URL = Base URL + /chat/completions
API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
# 官方文档：所有 Coding Plan 套餐均支持 GLM-5.3 / GLM-5.3-Flash
MODEL = "glm-5.3"


def main() -> None:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 GLM_KEY，请先执行 export GLM_KEY=你的Key", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "用一句话介绍 Python"}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        # 把服务端错误原样打到 stderr，便于排查（如 1113 表示没走到套餐额度）
        print(f"请求失败：HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    print(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
