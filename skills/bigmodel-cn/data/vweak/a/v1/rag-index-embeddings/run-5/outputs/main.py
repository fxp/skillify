#!/usr/bin/env python3
import os
import requests
import json
import numpy as np
from scipy.spatial.distance import cosine

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 读取faq.txt文件
with open('faq.txt', 'r', encoding='utf-8') as f:
    faq_lines = f.readlines()

# 使用智谱AI的embedding-3模型将每行文本向量化
vectors = []
for line in faq_lines:
    response = requests.post(
        'https://open.bigmodel.cn/api/paas/v4/embeddings',
        headers={'Authorization': f'Bearer {api_key}'},
        json={'model': 'embedding-3', 'text': line.strip()}
    )
    response.raise_for_status()
    vectors.append(response.json()['data']['vectors'])

# 使用'发票怎么开'这句话进行查询
query = '发票怎么开'
query_vector = requests.post(
    'https://open.bigmodel.cn/api/paas/v4/embeddings',
    headers={'Authorization': f'Bearer {api_key}'},
    json={'model': 'embedding-3', 'text': query}
).json()['data']['vectors']

# 计算余弦相似度并获取最相似的三个问题
cosine_similarities = []
for i, vector in enumerate(vectors):
    similarity = 1 - cosine(query_vector, vector)
    cosine_similarities.append((similarity, faq_lines[i].strip()))

cosine_similarities.sort(reverse=True)

# 打印最相似的三个问题
for i in range(3):
    print(cosine_similarities[i][1])
