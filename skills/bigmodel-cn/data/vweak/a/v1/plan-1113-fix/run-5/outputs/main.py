import os
import requests

# Read API Key from environment variable
api_key = os.environ['GLM_KEY']

# Prepare the request payload
payload = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "user",
            "content": "用一句话介绍 Python"
        }
    ]
}

# Make the request to the API
response = requests.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json=payload
)

# Print the response
print(response.json())