import os
import requests

# 从环境变量获取API Key
api_key = os.getenv('ZHIPUAI_API_KEY')

# API的Base URL
base_url = 'https://open.bigmodel.cn/api/paas/v4/'

# 定义查询参数
params = {
    'model': 'glm-5.3',
    'messages': [
        {
            'role': 'user',
            'content': '2026年智谱BigModel发布了哪些新模型？'}
    ]
}

# 发送请求
response = requests.post(base_url + 'chat/completions', headers={'Authorization': f'Bearer {api_key}'}, json=params)

# 检查请求是否成功
if response.status_code == 200:
    # 获取答案
    answer = response.json()['choices'][0]['message']['content']
    print(answer)
    # 打印信息来源
    print('信息来源: 智谱AI开放平台API')
else:
    print('请求失败，请检查API Key是否正确。')