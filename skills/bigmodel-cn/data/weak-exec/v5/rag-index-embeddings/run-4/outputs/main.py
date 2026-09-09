#!/usr/bin/env python3
import os
import json
import requests
import math

def read_faq(file_path):
    """读取FAQ文件，每行一条问题"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 去除每行末尾的换行符
    return [line.strip() for line in lines if line.strip()]

def get_embedding(text, model="embedding-3"):
    """使用智谱AI embedding-3模型获取文本向量"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "input": text
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()

    # 返回向量数据
    return result['data'][0]['embedding']

def cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    # 计算点积
    dot_product = sum(a * b for a, b in zip(vec1, vec2))

    # 计算向量的模
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    # 避免除零错误
    if magnitude1 == 0 or magnitude2 == 0:
        return 0

    return dot_product / (magnitude1 * magnitude2)

def main():
    # 读取FAQ文件
    faq_file = "faq.txt"
    faq_questions = read_faq(faq_file)

    print(f"读取到 {len(faq_questions)} 条FAQ问题")

    # 对每个FAQ问题进行向量化
    print("开始向量化FAQ问题...")
    vectors = []
    for i, question in enumerate(faq_questions):
        print(f"正在处理第 {i+1}/{len(faq_questions)} 条: {question[:30]}...")
        try:
            embedding = get_embedding(question)
            vectors.append({
                "index": i,
                "question": question,
                "vector": embedding
            })
        except Exception as e:
            print(f"处理第 {i+1} 条时出错: {e}")
            continue

    # 保存向量化结果到文件
    with open("vectors.json", "w", encoding="utf-8") as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)

    print(f"已保存 {len(vectors)} 条向量到 vectors.json")

    # 查询语句
    query = "发票怎么开"
    print(f"\n查询语句: {query}")

    # 获取查询语句的向量
    query_vector = get_embedding(query)
    print("已获取查询语句的向量")

    # 计算相似度并找出top-3
    similarities = []
    for item in vectors:
        sim = cosine_similarity(query_vector, item["vector"])
        similarities.append({
            "index": item["index"],
            "question": item["question"],
            "similarity": sim
        })

    # 按相似度降序排序
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    # 输出top-3
    print("\nTop 3 最相似的问题:")
    for i, item in enumerate(similarities[:3], 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   问题: {item['question']}")
        print()

if __name__ == "__main__":
    main()