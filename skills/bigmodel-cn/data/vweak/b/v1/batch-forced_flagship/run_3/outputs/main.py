#!/usr/bin/env python3
import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 构建JSONL文件
def create_jsonl_file(comments_file, jsonl_file):
    with open(comments_file, 'r', encoding='utf-8') as f:
        comments = f.readlines()
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for comment in comments:
            f.write(comment.strip() + '
')

# 上传JSONL文件到Zhipu AI
def upload_jsonl_to_zhipu(jsonl_file):
    url = "https://open.bigmodel.cn/api/paas/v4/batches"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "glm-5.3",
        "file": jsonl_file
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()['batch_id']

# 主函数
if __name__ == '__main__':
    comments_file = "comments.txt"
    jsonl_file = "comments.jsonl"
    create_jsonl_file(comments_file, jsonl_file)
    batch_id = upload_jsonl_to_zhipu(jsonl_file)
    print(batch_id)