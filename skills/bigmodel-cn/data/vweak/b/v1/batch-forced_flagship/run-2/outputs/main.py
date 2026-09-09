# main.py
import os
import requests

def main():
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = 'https://open.bigmodel.cn/api/paas/v4/batches'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'glm-5.3',
        'data': [

        ]
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    batch_id = response.json()['batch_id']
    print(batch_id)

if __name__ == '__main__':
    main()