import os
import json
import requests
import math
from typing import List, Dict, Any

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量之间的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度必须相同")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)

def load_faq_data(faq_path: str) -> List[str]:
    """加载 FAQ 数据"""
    with open(faq_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines

def generate_embedding(text: str, api_key: str) -> List[float]:
    """调用智谱 embedding API 生成文本向量"""
    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()
    return result["data"][0]["embedding"]

def process_faq_embeddings(faq_data: List[str], api_key: str) -> List[Dict[str, Any]]:
    """处理 FAQ 数据，生成所有向量化结果"""
    embeddings_data = []

    print(f"开始向量化 {len(faq_data)} 条 FAQ...")

    for i, text in enumerate(faq_data):
        print(f"处理第 {i+1}/{len(faq_data)} 条: {text[:30]}...")

        embedding = generate_embedding(text, api_key)
        embeddings_data.append({
            "index": i,
            "text": text,
            "embedding": embedding
        })

    return embeddings_data

def search_similar(query: str, embeddings_data: List[Dict[str, Any]], api_key: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """搜索与查询最相似的 FAQ"""
    # 1. 向量化查询
    query_embedding = generate_embedding(query, api_key)

    # 2. 计算相似度
    similarities = []
    for item in embeddings_data:
        similarity = cosine_similarity(query_embedding, item["embedding"])
        similarities.append({
            "index": item["index"],
            "text": item["text"],
            "similarity": similarity
        })

    # 3. 排序并取 top_k
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    return similarities[:top_k]

def main():
    # 设置 API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 文件路径
    faq_path = "../run-3/faq.txt"
    vectors_path = "vectors.json"

    try:
        # 1. 加载 FAQ 数据
        faq_data = load_faq_data(faq_path)
        print(f"成功加载 {len(faq_data)} 条 FAQ")

        # 2. 生成向量化结果
        embeddings_data = process_faq_embeddings(faq_data, api_key)

        # 3. 保存向量数据
        with open(vectors_path, 'w', encoding='utf-8') as f:
            json.dump(embeddings_data, f, ensure_ascii=False, indent=2)
        print(f"向量数据已保存到 {vectors_path}")

        # 4. 执行查询
        query = "发票怎么开"
        print(f"\n查询: '{query}'")

        similar_items = search_similar(query, embeddings_data, api_key)

        # 5. 输出结果
        print(f"\n最相似的 {len(similar_items)} 条 FAQ:")
        print("-" * 50)
        for i, item in enumerate(similar_items, 1):
            print(f"{i}. [相似度: {item['similarity']:.4f}] {item['text']}")

    except Exception as e:
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    main()