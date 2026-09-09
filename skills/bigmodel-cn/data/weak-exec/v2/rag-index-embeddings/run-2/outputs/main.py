#!/usr/bin/env python3
import os
import json
import math
import requests


def load_faq(file_path):
    """读取FAQ文件，返回问题列表"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
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

    return result["data"][0]["embedding"]


def cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0
    return dot_product / (magnitude1 * magnitude2)


def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 文件路径
    faq_file = "faq.txt"
    vectors_file = "vectors.json"

    # 加载FAQ
    faqs = load_faq(faq_file)
    print(f"加载了 {len(faqs)} 条FAQ")

    # 获取所有FAQ的向量
    embeddings = []
    for i, faq in enumerate(faqs):
        print(f"正在处理第 {i+1}/{len(faqs)} 条: {faq[:30]}...")
        embedding = get_embedding(faq, api_key)
        embeddings.append(embedding)

    # 保存向量到JSON文件
    vectors_data = {
        "model": "embedding-3",
        "dimensions": 1024,
        "data": [{"text": faq, "embedding": emb} for faq, emb in zip(faqs, embeddings)]
    }

    with open(vectors_file, 'w', encoding='utf-8') as f:
        json.dump(vectors_data, f, ensure_ascii=False, indent=2)
    print(f"向量已保存到 {vectors_file}")

    # 查询向量
    query = "发票怎么开"
    print(f"\n查询: {query}")

    query_embedding = get_embedding(query, api_key)

    # 计算相似度并排序
    similarities = []
    for i, (faq, embedding) in enumerate(zip(faqs, embeddings)):
        similarity = cosine_similarity(query_embedding, embedding)
        similarities.append((similarity, i, faq))

    # 按相似度降序排序，取前3
    similarities.sort(reverse=True, key=lambda x: x[0])
    top_3 = similarities[:3]

    # 输出结果
    print("\n最相关的3条FAQ:")
    for rank, (similarity, index, faq) in enumerate(top_3, 1):
        print(f"{rank}. 相似度: {similarity:.4f}")
        print(f"   问题: {faq}")
        print()


if __name__ == "__main__":
    main()