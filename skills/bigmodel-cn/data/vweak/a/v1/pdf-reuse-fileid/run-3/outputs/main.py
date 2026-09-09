import requests
import base64
import os

# Get API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# PDF file path
pdf_file_path = '/path/to/contract.pdf'

# Read PDF file and encode it to base64
with open(pdf_file_path, 'rb') as pdf_file:
    pdf_data = pdf_file.read()
    pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

# Define the API endpoint and parameters
api_url = 'https://open.bigmodel.cn/api/paas/v4/files'
headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}

# Upload PDF file to BigModel and get file ID
response = requests.post(api_url, headers=headers, json={'file': pdf_base64})
file_id = response.json()['file_id']

# Define the questions to ask
questions = ['What is the contract number?', 'What is the total amount of the contract?', 'How is the penalty calculated?']

# Ask questions and print answers
for question in questions:
    # Define the prompt
    prompt = {'model': 'glm-5.3', 'messages': [{'role': 'user', 'content': question}]}
    # Send the prompt to BigModel and get the response
    response = requests.post('https://open.bigmodel.cn/api/paas/v4/chat/completions', headers=headers, json=prompt)
    # Print the response
    print(response.json()['choices'][0]['message']['content'])
