#!/usr/bin/env python3

import os
import requests
import json
from sklearn.metrics.pairwise import cosine_similarity

# 读取向量文件
def read_vectors(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        vectors = []
        for line in file:
            vectors.append(json.loads(line))
    return vectors

# 查询函数
def query(file_path, query):
    vectors = read_vectors(file_path)
    query_vector = json.loads(query)
    similarities = []
    for v in vectors:
        similarity = cosine_similarity([query_vector], [v])[0][0]
        similarities.append((similarity, v['text']))
    similarities.sort(reverse=True)
    return similarities[:3]

# 主函数
if __name__ == '__main__':
    vectors_file = 'vectors.json'
    query_text = '发票怎么开'
    top_results = query(vectors_file, query_text)
    for _, text in top_results:
        print(text)
