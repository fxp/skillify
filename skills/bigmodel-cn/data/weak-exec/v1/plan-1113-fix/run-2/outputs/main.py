import os
import requests

# 从环境变量读取GLM Coding Plan API Key
api_key = os.environ.get("GLM_KEY")

if not api_key:
    print("错误：请设置GLM_KEY环境变量")
    exit(1)

# 使用Coding Plan的API端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "用一句话介绍 Python"
        }
    ]
}

try:
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    result = response.json()
    print(result["choices"][0]["message"]["content"])
except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"响应内容: {e.response.text}")