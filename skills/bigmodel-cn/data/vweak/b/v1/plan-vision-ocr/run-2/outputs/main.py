import os
import requests
import json

# API Key and Base URL for GLM Coding Plan
api_key = os.environ['GLM_CODING_PLAN_API_KEY']
base_url = 'https://open.bigmodel.cn/api/coding/paas/v4'

# Load image from the current directory
with open('invoice.png', 'rb') as image_file:
    image_data = image_file.read()

# Prepare the request data
data = {
    'model': 'glm-5.3',
    'messages': [
        {
            'role': 'user',
            'content': 'Describe the content of the invoice image.'
        }
    ],
    'stream': False
}

# Send the request to the API
response = requests.post(
    f'{base_url}/image/recognize',
    headers={'Authorization': f'Bearer {api_key}'},
    data=json.dumps(data),
    files={'image': ('invoice.png', image_data)}
)

# Check if the request was successful
if response.status_code == 200:
    print('Model used:', response.json()['model'])
    print('Server response:', response.json()['choices'][0]['message']['content'])
else:
    print('Error:', response.status_code, response.text)