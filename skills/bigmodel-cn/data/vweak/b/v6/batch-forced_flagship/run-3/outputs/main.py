#!/usr/bin/env python3

import os
import requests

# Set up API key and Base URL
api_key = os.environ['ZHIPUAI_API_KEY']
base_url = "https://open.bigmodel.cn/api/paas/v4"

# Function to create a batch
def create_batch(texts, model="glm-5.3", max_tokens=100):
    headers = {
        "Authorization": f"Bearer {api_key}`,
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": t
        } for t in texts]
    }
    response = requests.post(f "{base_url}/batches", headers=headers, json=data)
    response.raise_for_status()
    return response.json()["id"]

# Read comments from comments.txt
with open("comments.txt", "r", encoding="utf-8") as file:
    comments = file.readlines()

# Create a batch and print the batch ID
batch_id = create_batch(comments)
print("Batch ID:", batch_id)