import os, requests

# 从环境变量 GLM_KEY 获取 API Key
api_key = os.environ.get("GLM_KEY")

if not api_key:
    print("错误：请设置环境变量 GLM_KEY")
    exit(1)

# 使用 Coding Plan 的正确端点
url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 发送请求
response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": "用一句话介绍 Python"
            }
        ]
    }
)

# 检查响应
if response.status_code == 200:
    result = response.json()
    if "choices" in result and len(result["choices"]) > 0:
        print(result["choices"][0]["message"]["content"])
    else:
        print("响应格式异常")
        print(result)
else:
    print(f"请求失败，状态码: {response.status_code}")
    print(response.text)