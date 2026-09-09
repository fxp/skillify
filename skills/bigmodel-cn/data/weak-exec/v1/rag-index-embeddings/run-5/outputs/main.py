#!/usr/bin/env python3
import os
import json
import math
import requests


def read_faq(file_path):
    """读取FAQ文件，每行一个问答"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines


def get_embedding(text, api_key):
    """使用智谱AI embedding-3获取文本向量"""
    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text,
        "dimensions": 1024
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()
    return result['data'][0]['embedding']


def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must be of the same length")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("Error: ZHIPUAI_API_KEY environment variable not set")
        return

    # 读取FAQ文件（从上级目录）
    faq_file = '../../run-3/faq.txt'
    faq_lines = read_faq(faq_file)

    print(f"Read {len(faq_lines)} FAQ lines from {faq_file}")

    # 对每一行进行向量化
    vectors = []
    for i, line in enumerate(faq_lines):
        print(f"Processing line {i+1}/{len(faq_lines)}: {line[:30]}...")
        try:
            embedding = get_embedding(line, api_key)
            vectors.append({
                'text': line,
                'embedding': embedding,
                'index': i
            })
        except Exception as e:
            print(f"Error processing line {i+1}: {e}")

    # 保存向量到JSON文件
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(vectors)} vectors to vectors.json")

    # 查询向量
    query = "发票怎么开"
    print(f"\nQuery: {query}")

    try:
        query_embedding = get_embedding(query, api_key)
        print("Got query embedding")
    except Exception as e:
        print(f"Error getting query embedding: {e}")
        return

    # 计算相似度
    similarities = []
    for vec_data in vectors:
        similarity = cosine_similarity(query_embedding, vec_data['embedding'])
        similarities.append({
            'text': vec_data['text'],
            'similarity': similarity,
            'index': vec_data['index']
        })

    # 按相似度排序
    similarities.sort(key=lambda x: x['similarity'], reverse=True)

    # 输出top 3
    print("\nTop 3 most similar results:")
    for i, result in enumerate(similarities[:3]):
        print(f"{i+1}. Similarity: {result['similarity']:.4f}")
        print(f"   Text: {result['text']}\n")


if __name__ == "__main__":
    main()