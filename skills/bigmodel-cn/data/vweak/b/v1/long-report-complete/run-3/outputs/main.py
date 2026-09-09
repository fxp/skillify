#!/usr/bin/env python3

import os
import requests

# Get API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Define the URL for the API endpoint
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# Define the data payload
data = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "请生成一份关于2026年中国新能源汽车出口的市场简报，不少于600字，包含小标题和具体数据。"}
        ],
    "stream": false
}

# Make the API request
response = requests.post(url, headers={
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"}, json=data)

# Check for successful response
if response.status_code == 200:
    # Print the response content
    print(response.json()["choices"][0]["message"]["content"])
else:
    # Print error message
    print(f"Error: {response.status_code} - {response.text}")
