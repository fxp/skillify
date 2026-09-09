#!/usr/bin/env python3
import os
import json
import requests
import math
import time

def get_faq_lines():
    """读取faq.txt文件，返回每行内容"""
    faq_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v2/rag-index-embeddings/run-2/faq.txt"
    with open(faq_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines

def call_embedding_api(text):
    """调用智谱embedding-3 API获取向量"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("ZHIPUAI_API_KEY environment variable not set")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result
    except requests.exceptions.RequestException as e:
        print(f"API调用失败: {e}")
        return None

def compute_cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)

def main():
    # 读取FAQ文件
    print("读取FAQ文件...")
    faq_lines = get_faq_lines()
    print(f"共读取 {len(faq_lines)} 条FAQ")

    # 存储向量化结果
    vectors = []

    # 对每条FAQ进行向量化
    print("\n开始向量化FAQ...")
    for i, line in enumerate(faq_lines):
        print(f"处理第 {i+1}/{len(faq_lines)} 条: {line[:30]}...")

        # 调用embedding API
        result = call_embedding_api(line)
        if result and 'data' in result and len(result['data']) > 0:
            vector = result['data'][0]['embedding']
            vectors.append({
                'index': i,
                'text': line,
                'vector': vector
            })
        else:
            print(f"警告: 第 {i+1} 条FAQ向量化失败")

        # 避免API调用过于频繁
        time.sleep(0.1)

    # 保存向量数据
    print("\n保存向量数据...")
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(vectors)} 个向量到 vectors.json")

    # 使用"发票怎么开"进行查询
    query = "发票怎么开"
    print(f"\n使用查询词: '{query}'")

    # 获取查询向量
    print("获取查询向量...")
    query_result = call_embedding_api(query)
    if not query_result or 'data' not in query_result or len(query_result['data']) == 0:
        print("错误: 无法获取查询向量")
        return

    query_vector = query_result['data'][0]['embedding']

    # 计算相似度
    similarities = []
    for item in vectors:
        similarity = compute_cosine_similarity(query_vector, item['vector'])
        similarities.append({
            'text': item['text'],
            'similarity': similarity,
            'index': item['index']
        })

    # 按相似度排序并取top-3
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    top_3 = similarities[:3]

    # 打印结果
    print("\nTop-3 最相似的结果:")
    print("-" * 50)
    for i, item in enumerate(top_3, 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   原文: {item['text']}")
        print()

if __name__ == "__main__":
    main()