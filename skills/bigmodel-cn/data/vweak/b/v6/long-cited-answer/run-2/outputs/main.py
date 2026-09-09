# main.py

import requests
import os

def get_new能源汽车出口目的地国家():
    url = 'https://api.zhipu.ai/v1/search'
    headers = {'Authorization': 'Bearer ' + os.environ['ZHIPUAI_API_KEY']}
    params = {'query': '2026 年中国新能源汽车出口的主要目的地国家有哪些', 'page': 1, 'page_size': 10}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()['results']
    else:
        return []

if __name__ == '__main__':
    results = get_new能源汽车出口目的地国家()
    print(results)
