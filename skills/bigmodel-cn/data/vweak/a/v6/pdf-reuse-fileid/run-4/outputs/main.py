#!/usr/bin/env python3

import os
import requests

# Get API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Base URL for Zhipu AI API
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# Function to upload file and get file_id
def upload_file(file_path):
    files = {'file': open(file_path, 'rb')}
    response = requests.post(f'{base_url}/files', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/octet-stream'}, files=files)
    return response.json()['id']

# Function to ask questions and print answers
def ask_questions(file_id):
    questions = ['合同编号是什么', '合同总金额是多少', '违约金怎么算']
    for question in questions:
        response = requests.post(f'{base_url}/chat/completions', headers={'Authorization': f'Bearer {api_key}'}, json={'model': 'glm-5.3', 'messages': [{'role': 'user', 'content': [
            {'type': 'file', 'file': {'file_id': file_id}},
            {'type': 'text', 'text': question}
        ]}]}).json()
        print(question, response['choices'][0]['message']['content'])

# Main function
if __name__ == '__main__':
    file_path = 'contract.pdf'
    file_id = upload_file(file_path)
    ask_questions(file_id)