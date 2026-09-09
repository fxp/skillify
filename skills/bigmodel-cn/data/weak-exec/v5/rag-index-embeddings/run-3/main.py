#!/usr/bin/env python3
import os
import json
import requests
import math
from typing import List, Dict, Any

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
API_BASE = "https://open.bigmodel.cn/api/paas/v4"
EMBEDDING_MODEL = "embedding-3"
EMBEDDING_BATCH_SIZE = 64  # embedding-3 单次最多 64 条
EMBEDDING_DIMENSIONS = 2048  # embedding-3 默认维度

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have the same length")

    dot_product = 0.0
    norm1 = 0.0
    norm2 = 0.0

    for i in range(len(vec1)):
        dot_product += vec1[i] * vec2[i]
        norm1 += vec1[i] * vec1[i]
        norm2 += vec2[i] * vec2[i]

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))

def get_embeddings(texts: List[str], model: str = EMBEDDING_MODEL) -> List[List[float]]:
    """获取文本的向量表示"""
    if not API_KEY:
        raise ValueError("ZHIPUAI_API_KEY environment variable not set")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    all_embeddings = []

    # 分批处理
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]

        payload = {
            "model": model,
            "input": batch,
            "dimensions": EMBEDDING_DIMENSIONS
        }

        response = requests.post(
            f"{API_BASE}/embeddings",
            headers=headers,
            json=payload
        )

        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")

        result = response.json()

        if "data" not in result:
            raise Exception(f"Unexpected response format: {result}")

        # 提取向量
        batch_embeddings = [item["embedding"] for item in result["data"]]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings

def main():
    # 读取 FAQ 文件
    faq_file = "faq.txt"
    try:
        with open(faq_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: {faq_file} not found")
        return

    # 清理数据，去除序号和空白字符
    faq_questions = []
    for line in lines:
        line = line.strip()
        # 去除开头的序号（如 "1.", "2." 等）
        if '.' in line:
            line = line.split('.', 1)[1].strip()
        if line:  # 确保不为空
            faq_questions.append(line)

    print(f"Loaded {len(faq_questions)} FAQ questions")

    # 生成向量
    print("Generating embeddings...")
    embeddings = get_embeddings(faq_questions)

    if len(embeddings) != len(faq_questions):
        raise Exception(f"Number of embeddings ({len(embeddings)}) does not match number of questions ({len(faq_questions)})")

    # 保存到 JSON
    vectors_data = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "total_items": len(faq_questions),
        "embeddings": [
            {
                "text": text,
                "vector": vector
            }
            for text, vector in zip(faq_questions, embeddings)
        ]
    }

    with open("vectors.json", 'w', encoding='utf-8') as f:
        json.dump(vectors_data, f, ensure_ascii=False, indent=2)

    print(f"Vectors saved to vectors.json ({len(faq_questions)} items)")

    # 查询
    query = "发票怎么开"
    print(f"\nQuery: '{query}'")

    # 获取查询向量
    query_embeddings = get_embeddings([query])
    query_vector = query_embeddings[0]

    # 计算相似度
    similarities = []
    for i, (text, vector) in enumerate(zip(faq_questions, embeddings)):
        similarity = cosine_similarity(query_vector, vector)
        similarities.append((i, text, similarity))

    # 按相似度排序
    similarities.sort(key=lambda x: x[2], reverse=True)

    # 取 top 3
    top_3 = similarities[:3]

    print("\nTop 3 most similar questions:")
    for i, (idx, text, score) in enumerate(top_3, 1):
        print(f"{i}. (Similarity: {score:.4f}) {text}")

if __name__ == "__main__":
    main()