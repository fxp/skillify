#!/usr/bin/env python3
import os
import requests

# Load API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Define the base URL for the API
base_url = 'https://open.bigmodel.cn/api/'

# Define the endpoint for the search API
search_endpoint = 'chat/completions'

# Define the search prompt
prompt = '2026 年中国新能源汽车出口的主要目的地国家有哪些'

# Make the API request
response = requests.post(
    f'{base_url}{search_endpoint}',
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
    json={
        'model': 'glm-5.3',
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ],
    }
)

# Check if the request was successful
if response.status_code == 200:
    # Extract the answer from the response
    answer = response.json()['choices'][0]['message']['content']

    # Print the answer
    print(answer)
else:
    # Print an error message
    print('Error: Unable to fetch search results')
