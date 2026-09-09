#!/usr/bin/env python3

import os
import requests

# Load API Key from environment variable
api_key = os.environ['GLM_CODING_PLAN_API_KEY']

# Define the base URL for GLM Coding Plan
base_url = 'https://open.bigmodel.cn/api/coding/paas/v4'

# Function to analyze the invoice image and print the content
def analyze_invoice(image_path):
    # Prepare the API request
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'glm-5.3',
        'messages': [{
            'role': 'user',
            'content': f'请分析图片 {image_path} 并提取其中的内容。'
        }]
    }

    # Send the API request
    response = requests.post(f'{base_url}/chat/completions', headers=headers, json=data)

    # Check for errors
    if response.status_code != 200:
        print('Error:', response.status_code)
        return

    # Print the model used and the response content
    print('Used model:', response.json()['model'])
    print('Response:', response.json()['choices'][0]['message']['content'])

# Main entry point
if __name__ == '__main__':
    invoice_image_path = 'invoice.png'
    analyze_invoice(invoice_image_path)
