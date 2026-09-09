#!/usr/bin/env python3

import os
import requests

def main():
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = 'https://open.bigmodel.cn/api/v4/batches'

    data = {'input_file_id': 'example_input_file_id', 'endpoint': '/v4/chat/completions', 'completion_window': '24h'}
    headers = {'Authorization': f'Bearer {api_key}'}

    response = requests.post(url, headers=headers, json=data)
    print(response.json()['id'])

if __name__ == '__main__':
    main()