# This script generates a market report on the export of new energy vehicles in China in 2026.

import os
import requests

def generate_report():
    api_key = os.getenv('ZHIPUAI_API_KEY')
    url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = {
        'model': 'glm-5.3',
        'messages': [
            {
                'role': 'user',
                'content': '请生成一份关于2026年中国新能源汽车出口的市场简报，包含小标题和数据，不少于600字。'
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

if __name__ == '__main__':
    report = generate_report()
    print(report)
    print(len(report), 'Chinese characters')
