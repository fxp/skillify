# main.py

import os

import requests

# Read the API key from the environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# The base URL for the Batch API
base_url = 'https://open.bigmodel.cn/api/paas/v4/batches'

# Function to create a batch task
def create_batch_task(data):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    response = requests.post(base_url, headers=headers, json=data)
    return response.json()

# Main function
def main):
    # Construct the data for the batch request
    batch_data = {
        'model': 'glm-5.3',
        'messages': [
            {
                'role': 'user',
                'content': 'Hello, please introduce yourself.'
            }
        ]
    }

    # Create the batch task
    response = create_batch_task(batch_data)

    # Check if the task was created successfully
    if response.get('status') == 'success':
        # Print the batch task ID
        print(response['data']['batch_id'])
    else:
        # Print an error message
        print('Failed to create batch task.')
