#!/usr/bin/env python3

import requests

# Read the API key from the environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# The endpoint for searching the knowledge base
search_endpoint = 'https://open.bigmodel.cn/api/paas/v4/knowledge/search'

# The query to search for
query = '退换货政策的有效期是多久'

# Make the API request
response = requests.post(search_endpoint, headers={'Authorization': f'Bearer {api_key}'}, json={'query': query})

# Check if the request was successful
if response.status_code == 200:
    # Parse the response
    results = response.json()
    # Extract the relevant information
    for result in results['results']:
        print('原文片段:', result['text'])
else:
    print('Failed to retrieve results')
