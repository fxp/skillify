import os
import requests

# 从环境变量读取 GLM Key
glm_key = os.environ.get('GLM_KEY')

if not glm_key:
    print("错误：请设置环境变量 GLM_KEY")
    exit(1)

# 使用 Coding Plan 的正确端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

headers = {
    "Authorization": f"Bearer {glm_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()
    print(result["choices"][0]["message"]["content"])
except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"响应状态码: {e.response.status_code}")
        print(f"响应内容: {e.response.text}")
except KeyError as e:
    print(f"响应解析失败，缺少字段: {e}")
    print(f"完整响应: {response.json()}")