#!/usr/bin/env python3

import os
import requests

# API Base URL
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# API Key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Model to use
model = 'glm-5.3'

# Prompt for the market brief
prompt = 'Write a 600-word market brief on the export of new energy vehicles in China in 2026. Include subheadings and specific data. The brief should be complete and suitable for inclusion in a weekly report.'

# Function to call the API and generate the brief
def generate_market_brief(prompt):
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    data = {'model': model, 'messages': [{'role': 'user', 'content': prompt}]}
    response = requests.post(f'{base_url}/chat/completions', headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

# Generate the market brief
market_brief = generate_market_brief(prompt)

# Check if the length of the market brief is at least 600 words
if len(market_brief) < 600:
    raise ValueError('The generated market brief is too short.')

# Print the market brief
print(market_brief)