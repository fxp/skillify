import os
import requests

# Replace 'your_api_key' with your actual API Key from the Zhipu AI console
api_key = os.environ['ZHIPUAI_API_KEY']

url = 'https://open.bigmodel.cn/api/coding/paas/v4/chat/completions'
headers = {'Authorization': f'Bearer {api_key}'}
messages = [{"role": "user", "content": "用一句话介绍 Python"}]

response = requests.post(url, headers=headers, json={'model': 'glm-5.3', 'messages': messages})
if response.status_code == 200:
    print(response.json()['choices'][0]['message']['content'])
else:
    print('Error:', response.status_code, response.json())