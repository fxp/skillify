#!/usr/bin/env python3

import os
import requests

def get_api_key():
    return os.environ['ZHIPUAI_API_KEY']

def main():
    file_id = 'contract.pdf'
    model = 'glm-5.3'
    api_key = get_api_key()
    base_url = 'https://open.bigmodel.cn/api/paas/v4'

    # Read the PDF file
    with open(file_id, 'rb') as f:
        file_content = f.read()

    # Upload the PDF file
    upload_url = f'{base_url}/files'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'file': file_content
    }
    response = requests.post(upload_url, headers=headers)
    response.raise_for_status()
    file_info = response.json()
    file_id = file_info['file_id']

    # Ask the first question
    question_url = f'{base_url}/files/{file_id}/process'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': 'What is the contract number?'
        }]
    }
    response = requests.post(question_url, headers=headers)
    response.raise_for_status()
    answer = response.json()['choices'][0]['message']['content']
    print(answer)

    # Ask the second question
    question_url = f'{base_url}/files/{file_id}/process'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': 'What is the total amount of the contract?'
        }]
    }
    response = requests.post(question_url, headers=headers)
    response.raise_for_status()
    answer = response.json()['choices'][0]['message']['content']
    print(answer)

    # Ask the third question
    question_url = f'{base_url}/files/{file_id}/process'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': 'How is the penalty calculated?'
        }]
    }
    response = requests.post(question_url, headers=headers)
    response.raise_for_status()
    answer = response.json()['choices'][0]['message']['content']
    print(answer)

if __name__ == '__main__':
    main()