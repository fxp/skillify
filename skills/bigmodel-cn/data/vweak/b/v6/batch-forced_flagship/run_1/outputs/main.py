#!/usr/bin/env python3

import os
import requests
import json

# 读取 API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 构造 JSONL 文件内容
comments = []
with open('/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/vweak/b/v6/batch_forced_flagship/run_1/comments.txt', 'r', encoding='utf-8') as file:
    for line in file:
        comments.append(json.dumps({'text': line.strip()}))

# 创建 JSONL 文件
with open('/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/vweak/b/v6/batch_forced_flagship/run_1/comments.jsonl', 'w', encoding='utf-8') as file:
    for comment in comments:
        file.write(comment + '\n')

# 上传文件
response = requests.post('https://open.bigmodel.cn/api/files', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, data={'purpose': 'user_data', 'files': ('comments.jsonl', open('/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/vweak/b/v6/batch_forced_flagship/run_1/comments.jsonl', 'rb'), 'file_type': 'jsonl'})
if response.status_code == 200:
    file_id = response.json()['id']
else:
    print('上传失败')
    exit(1)

# 创建 Batch
response = requests.post('https://open.bigmodel.cn/api/batches', headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, json={'input_file_id': file_id, 'endpoint': '/v4/chat/completions', 'completion_window': '24h'})
if response.status_code == 200:
    print('batch id:', response.json()['id'])
else:
    print('创建 Batch 失败')
    exit(1)
