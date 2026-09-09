#!/usr/bin/env python3
import os
import requests

# Retrieve API Key and KB ID from environment variables
api_key = os.environ['ZHIPUAI_API_KEY']
kbid = os.environ['ZHIPU_KB_ID']

# API endpoint for knowledge base validation
url = f'https://open.bigmodel.cn/api/paas/v4/knowledgebase/validate/{kbid}'

# Headers for the request
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

# Request data
data = {
    'model': 'glm-5.3',
}

# Send the request
response = requests.post(url, headers=headers, json=data)

# Check the response and print the validation result
if response.status_code == 200:
    print('Knowledge base is valid and usable.')
else:
    print('Knowledge base is invalid or not usable.')
