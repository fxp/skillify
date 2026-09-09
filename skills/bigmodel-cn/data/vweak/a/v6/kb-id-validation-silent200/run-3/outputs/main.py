#!/usr/bin/env python3
import os
import requests

def check_kb_exists(kb_id, api_key):
    url = f'https://open.bigmodel.cn/api/paas/v4/knowledge-bases/{kb_id}'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)
    return response.status_code == 200

if __name__ == '__main__':
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not kb_id or not api_key:
        print('环境变量ZHIPU_KB_ID或ZHIPUAI_API_KEY未设置')
        exit(1)
    if check_kb_exists(kb_id, api_key):
        print('知识库存在且可用')
    else:
        print('知识库不存在或不可用')
