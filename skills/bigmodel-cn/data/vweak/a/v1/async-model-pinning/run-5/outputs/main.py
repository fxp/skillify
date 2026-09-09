#!/usr/bin/env python3

import os
import requests

def main():
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
    model = 'glm-4.6'
    messages = [{'role': 'user', 'content': 'This is the first sentence for sentiment analysis.'},
               {'role': 'user', 'content': 'This is the second sentence for sentiment analysis.'},
               {'role': 'user', 'content': 'This is the third sentence for sentiment analysis.'}]
    headers = {'Authorization': f'Bearer {api_key}'}
    data = {'model': model, 'messages': messages}

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    # Print the model requested and the model used
    requested_model = model
    used_model = response.json()['model']
    print(f'我请求的模型: {requested_model}')
    print(f'接口实际使用的模型: {used_model}')

if __name__ == '__main__':
    main()