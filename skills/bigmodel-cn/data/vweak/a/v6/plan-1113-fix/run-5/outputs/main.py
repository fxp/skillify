# 修改后的 main.py
import os
import requests

# 读取环境变量中的 GLM_KEY
GLM_KEY = os.environ['GLM_KEY']

# 构造请求头
headers = {
    'Authorization': f'Bearer {GLM_KEY}',
}

# 构造请求数据
data = {
    'model': 'glm-5.3',
    'messages': [
        {
            'role': 'user',
            'content': '用一句话介绍 Python',
        }
    ],
}

# 发送请求
response = requests.post(
    'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    headers=headers,
    json=data
)

# 打印结果
print(response.json()['choices'][0]['message']['content'])