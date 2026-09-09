import os
import requests

# 使用 GLM Coding Plan 的端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 从环境变量读取 GLM_KEY
api_key = os.environ.get("GLM_KEY")

if not api_key:
    print("错误：请设置 GLM_KEY 环境变量")
    exit(1)

# 发送请求
response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
    }
)

# 检查响应
if response.status_code == 200:
    result = response.json()
    if "choices" in result and len(result["choices"]) > 0:
        print(result["choices"][0]["message"]["content"])
    else:
        print("错误：响应格式异常")
        print(result)
else:
    print(f"错误：HTTP {response.status_code}")
    print(response.text)