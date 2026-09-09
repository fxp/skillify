import os, requests

# 从环境变量读取 GLM_KEY
api_key = os.environ.get('GLM_KEY')
if not api_key:
    print("错误：请设置环境变量 GLM_KEY")
    exit(1)

# 使用编程套餐的端点（不是标准的 /paas/v4）
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "model": "glm-5.3",  # 编程套餐支持的模型
    "messages": [
        {
            "role": "user",
            "content": "用一句话介绍 Python"
        }
    ],
    "stream": False
}

response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()

result = response.json()
print(result["choices"][0]["message"]["content"])