import os
import requests

def check_knowledge_base():
    kb_id = os.environ['ZHIPU_KB_ID']
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = f'https://api.zhipu.ai/knowledgebase/check?kb_id={kb_id}'
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'valid':
            print('Knowledge base is valid and usable.')
        else:
            print('Knowledge base is invalid or not usable.')
    else:
        print('Failed to check knowledge base. Status code:', response.status_code)

if __name__ == '__main__':
    check_knowledge_base()