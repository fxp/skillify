# main.py

import os
import requests

# Load API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Define the endpoint URL
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# Prepare the request payload
payload = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "请生成一份关于2026年中国新能源汽车出口的市场简报。"}
        ]
}

# Make the request
response = requests.post(url, headers={
    "Authorization": f"Bearer {api_key}"
}, json=payload)

# Check for successful response
if response.status_code == 200:
    completions = response.json().get("choices", [])
    if completions:
        report = completions[0].get("message", "")
        print(report)
        print("Total words:", len(report.split()))
    else:
        print("No completions found.")
else:
    print("Failed to generate the report. Please check the API key and try again.")