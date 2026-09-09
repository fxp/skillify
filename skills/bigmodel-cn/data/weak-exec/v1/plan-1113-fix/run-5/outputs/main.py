import os, requests

# 使用GLM Coding Plan专用端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 从环境变量读取GLM_KEY
api_key = os.environ.get("GLM_KEY")

if not api_key:
    print("错误：请设置GLM_KEY环境变量")
    exit(1)

# 请求头
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 请求体
data = {
    "model": "glm-5.3",  # GLM Coding Plan支持的模型
    "messages": [{"role": "user", "content": "用一句话介绍 Python"}]
}

# 发送请求
try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()  # 检查HTTP错误

    # 打印模型回答
    result = response.json()
    print(result["choices"][0]["message"]["content"])

except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if e.response:
        print(f"错误信息: {e.response.text}")