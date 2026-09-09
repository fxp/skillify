# main.py

import os
import requests

# Read the API key from the environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Define the endpoint for the API
url = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'

# Define the headers
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {api_key}',
}

# Define the data payload
data = {
    'model': 'glm-5.3',
    'messages': [
        {
            'role': 'user',
            'content': '2026年中国新能源汽车出口市场简报',
        },
    ],
}

# Make the API request
response = requests.post(url, headers=headers, json=data)

# Check the status code of the response
if response.status_code == 200:
    # Extract the response text
    response_text = response.json()['choices'][0]['message']['content']
    # Print the response text
    print(response_text)
    # Print the length of the response text
    print('Actual length of the response:', len(response_text))
else:
    # Print the error message
    print('Error:', response.status_code, response.json()['error_message'])
