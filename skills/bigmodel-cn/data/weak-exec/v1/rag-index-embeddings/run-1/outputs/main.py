#!/usr/bin/env python3
"""
FAQ 向量化检索脚本
使用智谱 embedding-3 模型对 FAQ 文本进行向量化，实现相似度搜索
"""

import os
import json
import math
import requests

def load_faq(file_path):
    """加载 FAQ 文件，每行一个问题"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 清理每行文本，去除首尾空白
    faqs = [line.strip() for line in lines if line.strip()]
    return faqs

def get_embedding(text, api_key):
    """使用智谱 embedding-3 获取文本向量"""
    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text,
        "dimensions": 2048
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()

    # 返回第一个向量的值（我们每次只传一个文本）
    return result['data'][0]['embedding']

def cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def save_embeddings(faqs, embeddings, output_file):
    """保存向量化结果到 JSON 文件"""
    data = {
        "model": "embedding-3",
        "dimensions": len(embeddings[0]),
        "total_faqs": len(faqs),
        "embeddings": []
    }

    for i, (faq, embedding) in enumerate(zip(faqs, embeddings)):
        data["embeddings"].append({
            "index": i,
            "faq": faq,
            "embedding": embedding
        })

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已保存 {len(faqs)} 个 FAQ 向量到 {output_file}")

def main():
    # 文件路径
    faq_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    output_file = "vectors.json"

    # 检查 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 加载 FAQ
    print("正在加载 FAQ 文件...")
    faqs = load_faq(faq_file)
    print(f"加载了 {len(faqs)} 个 FAQ 问题")

    # 获取每个 FAQ 的向量
    print("开始向量化 FAQ...")
    embeddings = []

    for i, faq in enumerate(faqs):
        print(f"正在处理第 {i+1}/{len(faqs)} 个: {faq[:30]}...")
        embedding = get_embedding(faq, api_key)
        embeddings.append(embedding)

    # 保存向量化结果
    save_embeddings(faqs, embeddings, output_file)

    # 查询示例
    query = "发票怎么开"
    print(f"\n正在查询: '{query}'")

    # 获取查询向量
    query_embedding = get_embedding(query, api_key)

    # 计算相似度
    similarities = []
    for i, (faq, embedding) in enumerate(zip(faqs, embeddings)):
        similarity = cosine_similarity(query_embedding, embedding)
        similarities.append((i, similarity, faq))

    # 排序并取 top 3
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_3 = similarities[:3]

    # 输出结果
    print("\nTop 3 最相似的问题:")
    for i, (index, similarity, faq) in enumerate(top_3, 1):
        print(f"{i}. 相似度: {similarity:.4f}")
        print(f"   问题: {faq}")
        print()

if __name__ == "__main__":
    main()