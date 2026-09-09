#!/usr/bin/env python3
"""
FAQ 向量检索系统
使用智谱AI embedding-3 模型将FAQ问题向量化，实现语义检索
"""

import os
import json
import math
import requests

# API 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

def load_faq(filename="faq.txt"):
    """加载FAQ文件，返回问题列表"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # 去除每行的空白字符，过滤空行
        questions = [line.strip() for line in lines if line.strip()]
        print(f"加载了 {len(questions)} 个FAQ问题")
        return questions
    except FileNotFoundError:
        print(f"错误: 文件 {filename} 不存在")
        return []

def get_embeddings(texts, model="embedding-3", dimensions=1024):
    """使用智谱AI embedding-3 获取文本向量"""
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        return []

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # 准备请求数据
    data = {
        "model": model,
        "input": texts
    }

    # embedding-3 支持自定义维度
    if model == "embedding-3" and dimensions in [256, 512, 1024, 2048]:
        data["dimensions"] = dimensions

    try:
        print("正在调用 embedding API...")
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()

        result = response.json()

        # 检查响应状态
        if "data" not in result:
            print(f"API响应错误: {result}")
            return []

        # 提取向量
        embeddings = [item["embedding"] for item in result["data"]]
        print(f"成功获取 {len(embeddings)} 个向量")
        return embeddings

    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应内容: {e.response.text}")
        return []

def save_embeddings(vectors, filename="vectors.json"):
    """将向量和原始问题保存到JSON文件"""
    data = {
        "model": "embedding-3",
        "dimensions": len(vectors[0]) if vectors else 0,
        "total_questions": len(vectors),
        "embeddings": vectors
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"向量已保存到 {filename}")

def cosine_similarity(vector1, vector2):
    """计算两个向量的余弦相似度"""
    if len(vector1) != len(vector2):
        return 0

    dot_product = 0
    norm1 = 0
    norm2 = 0

    for i in range(len(vector1)):
        dot_product += vector1[i] * vector2[i]
        norm1 += vector1[i] ** 2
        norm2 += vector2[i] ** 2

    if norm1 == 0 or norm2 == 0:
        return 0

    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))

def search_similar(query, question_embeddings, questions, top_k=3):
    """搜索与查询最相似的问题"""
    if not question_embeddings:
        return []

    # 获取查询的向量
    query_embedding = get_embeddings([query])
    if not query_embedding:
        return []

    similarities = []

    # 计算每个问题与查询的相似度
    for i, embedding in enumerate(question_embeddings):
        similarity = cosine_similarity(query_embedding[0], embedding)
        similarities.append((similarity, i))

    # 按相似度排序（降序）
    similarities.sort(reverse=True, key=lambda x: x[0])

    # 返回 top_k 个最相似的结果
    top_results = similarities[:top_k]

    return [(similarity, questions[index]) for similarity, index in top_results]

def main():
    """主函数"""
    print("=== FAQ 向量检索系统 ===")

    # 1. 加载FAQ
    questions = load_faq()
    if not questions:
        print("没有找到FAQ问题，退出程序")
        return

    # 2. 获取所有FAQ的向量
    embeddings = get_embeddings(questions)
    if not embeddings:
        print("无法获取向量，退出程序")
        return

    # 3. 保存向量
    save_embeddings(embeddings)

    # 4. 查询示例
    query = "发票怎么开"
    print(f"\n查询: {query}")

    # 5. 搜索相似问题
    results = search_similar(query, embeddings, questions, top_k=3)

    # 6. 显示结果
    print(f"\n最相似的 {len(results)} 个问题:")
    for i, (score, question) in enumerate(results, 1):
        print(f"{i}. 相似度: {score:.4f}")
        print(f"   问题: {question}")
        print()

if __name__ == "__main__":
    main()