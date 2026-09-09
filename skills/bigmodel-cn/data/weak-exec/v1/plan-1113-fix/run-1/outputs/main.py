import os
import requests

url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
headers = {
    "Authorization": f"Bearer {os.environ['GLM_KEY']}",
    "Content-Type": "application/json"
}
data = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

response = requests.post(url, headers=headers, json=data)
response.raise_for_status()
result = response.json()
print(result["choices"][0]["message"]["content"])