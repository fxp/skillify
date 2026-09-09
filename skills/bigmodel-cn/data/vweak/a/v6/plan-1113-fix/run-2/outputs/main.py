import os
import requests

# 获取环境变量中的 GLM_KEY
api_key = os.environ.get('GLM_KEY')
if not api_key:
    print('Error: GLM_KEY environment variable is not set.')
    exit(1)

# 发送请求到模型并获取响应
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
headers = {'Authorization': f'Bearer {api_key}'}
messages = [{'role': 'user', 'content': '用一句话介绍 Python'}]
response = requests.post(url, headers=headers, json={'model': 'glm-5.3', 'messages': messages})

# 打印模型回答
print(response.json()['choices'][0]['text'])