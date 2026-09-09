#!/usr/bin/env python3

import os
import requests

# Read the KB ID and API Key from environment variables
kb_id = os.getenv('ZHIPU_KB_ID')
api_key = os.getenv('ZHIPUAI_API_KEY')

# Validate the knowledge base
def validate_knowledge_base(kb_id, api_key):
    url = f'https://open.bigmodel.cn/api/paas/v4/knowledge-bases/{kb_id}'
    headers = {'Authorization': f'Bearer {api_key}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print(f'Knowledge base {kb_id} exists and is usable.')
    else:
        print(f'Knowledge base {kb_id} does not exist or is not usable.')

# Main function
if __name__ == '__main__':
    validate_knowledge_base(kb_id, api_key)