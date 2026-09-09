#!/usr/bin/env python3
import os
import json
import requests
import math
from typing import List, Tuple

def load_faq(file_path: str) -> List[str]:
    """加载FAQ文件，每行作为一个问题"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.read().strip().split('\n')
        # 过滤空行
        return [line.strip() for line in lines if line.strip()]

def get_embedding(text: str, model: str = "embedding-3") -> List[float]:
    """获取单个文本的embedding向量"""
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

    if 'data' not in result or len(result['data']) == 0:
        raise ValueError(f"获取embedding失败: {result}")

    return result['data'][0]['embedding']

def batch_embed(texts: List[str], model: str = "embedding-3", batch_size: int = 64) -> List[List[float]]:
    """批量获取文本embedding向量"""
    all_embeddings = []

    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 分批处理
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        data = {
            "model": model,
            "input": batch_texts
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        if 'data' not in result:
            raise ValueError(f"第 {i//batch_size + 1} 批获取embedding失败: {result}")

        batch_embeddings = [item['embedding'] for item in result['data']]
        all_embeddings.extend(batch_embeddings)

    # 验证数量
    if len(all_embeddings) != len(texts):
        raise ValueError(f"期望 {len(texts)} 个向量，实际得到 {len(all_embeddings)} 个")

    return all_embeddings

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def find_similar_questions(query: str, embeddings: List[List[float]], faq_questions: List[str], top_k: int = 3) -> List[Tuple[str, float]]:
    """查找与查询最相似的问题"""
    # 获取查询的embedding
    query_embedding = get_embedding(query)

    # 计算相似度
    similarities = []
    for i, embedding in enumerate(embeddings):
        similarity = cosine_similarity(query_embedding, embedding)
        similarities.append((faq_questions[i], similarity))

    # 按相似度排序并返回top_k
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_k]

def main():
    # 文件路径
    faq_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    vectors_file = "vectors.json"

    # 加载FAQ
    print("加载FAQ文件...")
    faq_questions = load_faq(faq_file)
    print(f"加载了 {len(faq_questions)} 个问题")

    # 批量获取embedding
    print("生成向量...")
    embeddings = batch_embed(faq_questions)
    print(f"生成了 {len(embeddings)} 个向量")

    # 保存到文件
    print("保存向量到文件...")
    vectors_data = {
        "model": "embedding-3",
        "total_questions": len(faq_questions),
        "embeddings": embeddings,
        "questions": faq_questions
    }

    with open(vectors_file, 'w', encoding='utf-8') as f:
        json.dump(vectors_data, f, ensure_ascii=False, indent=2)

    print(f"向量已保存到 {vectors_file}")

    # 查询相似问题
    query = "发票怎么开"
    print(f"\n查询: '{query}'")
    print("寻找最相似的问题...")

    similar_questions = find_similar_questions(query, embeddings, faq_questions, top_k=3)

    # 输出结果
    print("\nTop 3 最相似的问题:")
    for i, (question, similarity) in enumerate(similar_questions, 1):
        print(f"{i}. (相似度: {similarity:.4f}) {question}")

if __name__ == "__main__":
    main()