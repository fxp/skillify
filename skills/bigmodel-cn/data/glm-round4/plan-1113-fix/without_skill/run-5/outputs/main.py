"""用 GLM Coding Plan 套餐额度问模型"用一句话介绍 Python"，把回答打印到 stdout。

原代码一直报 429 {"code": "1113", "message": "余额不足或无可用资源包"} 的原因：
1. 端点不对：Coding Plan 的资源包只抵扣编程套餐专属端点
   https://open.bigmodel.cn/api/coding/paas/v4/...（官方文档「快速开始」中的
   OpenAI Chat Completion 协议接入地址）。原代码打的 /api/paas/v4/... 是
   按量计费的通用 API，不走套餐额度，账户里又没有现金余额，于是报 1113——
   并不是套餐额度用完了。
2. Key 取错了：os.environ[chr(39)+chr(39)] 实际读的是名为 "''" 的环境变量，
   永远取不到真正的 Key；应读 GLM_KEY。

运行方式：
    GLM_KEY=你的APIKey python3 main.py
"""

import os
import sys

import requests

# Coding Plan 套餐专属的 OpenAI 兼容端点（区别于按量计费的 /api/paas/v4）
URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
# 官方文档：所有 Coding Plan 套餐均支持 GLM-5.3 / GLM-5.3-Flash
MODEL = "glm-5.3"


def main() -> None:
    api_key = os.environ.get("GLM_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 GLM_KEY，例如：GLM_KEY=xxx.xxx python3 main.py")

    resp = requests.post(
        URL,
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

    try:
        data = resp.json()
    except ValueError:
        sys.exit(f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:500]!r}")

    if resp.status_code != 200 or "choices" not in data:
        # 把服务端原始错误完整带出来，便于排查（1113 通常意味着走错了端点）
        sys.exit(f"HTTP {resp.status_code}：{data}")

    print(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
