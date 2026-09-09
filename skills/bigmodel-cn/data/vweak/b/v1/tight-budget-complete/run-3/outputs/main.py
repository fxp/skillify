#!/usr/bin/env python3
import requests
import os

# Define the API endpoint and parameters
api_endpoint = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
api_key = os.environ["ZHIPUAI_API_KEY"]

# Function to call the API and generate the report
def generate_report():
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"}
    data = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": "请生成一份关于2026年中国新能源汽车出口的市场简报。"}
        ]
    }
    response = requests.post(api_endpoint, headers=headers, json=data)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# Generate the report
report = generate_report()
print(report)
# Print the length of the report
print(len(report))
