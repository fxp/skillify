import os
import requests

# Read API key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Base URL for BigModel API
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# Function to get answer from BigModel API
def get_answer(question):
    headers = {'Authorization': f'Bearer {api_key}'}
    data = {'model': 'glm-5.3', 'messages': [{'role': 'user', 'content': question}]}
    response = requests.post(f'{base_url}/chat/completions', headers=headers, json=data)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

# Main function
def main():
    question = '2026年智谱BigModel发布了哪些新模型'
    answer = get_answer(question)
    print(answer)

if __name__ == '__main__':
    main()