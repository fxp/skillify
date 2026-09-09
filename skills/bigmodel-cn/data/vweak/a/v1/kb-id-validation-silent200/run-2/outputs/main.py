# main.py

import os
import requests

# Read API Key and KB ID from environment variables
api_key = os.environ['ZHIPUAI_API_KEY']
kb_id = os.environ['ZHIPU_KB_ID']

# Base URL for Zhipu AI API
base_url = "https://open.bigmodel.cn/api/paas/v4"

# Endpoint for knowledge base operations
kb_endpoint = f "{base_url}/knowledge/{kb_id}"

# Check if the knowledge base exists and is usable
response = requests.get(kb_endpoint, headers={'Authorization': f"Bearer {api_key}"})
if response.status_code == 200:
    print("Knowledge base is valid.")
else:
    print("Knowledge base is invalid.")
