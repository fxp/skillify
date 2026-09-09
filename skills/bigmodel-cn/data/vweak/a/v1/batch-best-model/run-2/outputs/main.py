#!/usr/bin/env python3
import os
import requests

# Read API key from environment variable
API_KEY = os.environ['ZHIPUAI_API_KEY']

# Prepare the input data
input_data = "[\n\n\"" + \"\".join(open("comments.txt", "r").readlines()) + \"\"" + "]"

# Set up the URL for the chat completions endpoint
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# Set up the headers for the request
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# Set up the body for the request
body = {
    "model": "glm-5.3",
    "messages": [
        {
            "role": "system",
            "content": " classify the sentiment of the comments "
        },
        {
            "role": "user",
            "content": input_data
        }
    ]
}

# Send the request
response = requests.post(url, headers=headers, json=body)

# Check the response status
if response.status_code == 200:
    # Extract the task ID from the response
    batch_task_id = response.json()["id"]
    print(batch_task_id)
else:
    # Print the error message
    print(f"Error: {response.status_code}")
