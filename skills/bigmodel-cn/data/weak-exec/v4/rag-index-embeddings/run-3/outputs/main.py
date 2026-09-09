#!/usr/bin/env python3
import os
import json
import requests
import math

# 读取环境变量中的 API Key
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 读取 faq.txt 文件
faq_file_path = 'faq.txt'
with open(faq_file_path, 'r', encoding='utf-8') as f:
    faqs = [line.strip() for line in f.readlines() if line.strip()]

# API endpoint
EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

def get_embedding(text, model="embedding-3", dimensions=2048):
    """获取文本的向量表示"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "input": text,
        "dimensions": dimensions
    }

    response = requests.post(EMBEDDING_URL, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    return result["data"][0]["embedding"]

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def main():
    print("开始向量化 FAQ 数据...")

    # 将每一行 FAQ 向量化
    embeddings = []
    for i, faq in enumerate(faqs):
        print(f"处理 {i+1}/{len(faqs)}: {faq[:30]}...")
        embedding = get_embedding(faq)
        embeddings.append({
            "index": i,
            "text": faq,
            "embedding": embedding
        })

    # 保存向量到文件
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(embeddings, f, ensure_ascii=False, indent=2)

    print(f"\n向量化完成，共处理 {len(embeddings)} 条数据")
    print("向量数据已保存到 vectors.json")

    # 查询
    query = "发票怎么开"
    print(f"\n查询: {query}")

    # 获取查询向量
    query_embedding = get_embedding(query)

    # 计算相似度
    similarities = []
    for item in embeddings:
        similarity = cosine_similarity(query_embedding, item["embedding"])
        similarities.append({
            "index": item["index"],
            "text": item["text"],
            "similarity": similarity
        })

    # 按相似度排序
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    # 输出 top 3
    print("\nTop 3 最相关的问题：")
    for i, item in enumerate(similarities[:3], 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   问题: {item['text']}\n")

if __name__ == "__main__":
    main()