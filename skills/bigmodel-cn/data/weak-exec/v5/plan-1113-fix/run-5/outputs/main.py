import os
import requests

# 从环境变量 GLM_KEY 读取 API Key
api_key = os.environ.get("GLM_KEY")
if not api_key:
    print("错误：请设置环境变量 GLM_KEY")
    exit(1)

# 使用 Coding Plan 的端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "用一句话介绍 Python"
        }
    ],
    "stream": False
}

try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()

    # 打印模型的回答
    print(result["choices"][0]["message"]["content"])

except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if e.response is not None:
        print(f"响应状态码: {e.response.status_code}")
        print(f"响应内容: {e.response.text}")
except KeyError as e:
    print(f"解析响应失败，缺少字段: {e}")
    print(f"完整的响应: {result}")