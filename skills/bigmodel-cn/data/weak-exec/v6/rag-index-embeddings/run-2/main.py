import os
import json
import math
import requests
from typing import List, Dict, Tuple

def read_faq(file_path: str) -> List[str]:
    """读取faq文件，每行作为一个条目"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines

def get_embedding(text: str, model: str = "embedding-3") -> List[float]:
    """获取文本的embedding向量"""
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "input": [text]
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()
    return result["data"][0]["embedding"]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """计算两个向量的余弦相似度"""
    if len(v1) != len(v2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)

def main():
    # 1. 读取faq文件
    faq_file = "faq.txt"
    faq_questions = read_faq(faq_file)
    print(f"读取了 {len(faq_questions)} 条FAQ问题")

    # 2. 计算每个问题的embedding
    embeddings = []
    for i, question in enumerate(faq_questions):
        print(f"处理第 {i+1}/{len(faq_questions)} 条: {question[:30]}...")
        embedding = get_embedding(question)
        embeddings.append({
            "index": i,
            "text": question,
            "embedding": embedding
        })

    # 3. 保存结果到vectors.json
    with open("vectors.json", "w", encoding="utf-8") as f:
        json.dump(embeddings, f, ensure_ascii=False, indent=2)
    print("向量数据已保存到 vectors.json")

    # 4. 查询"发票怎么开"
    query = "发票怎么开"
    print(f"\n查询问题: {query}")

    query_embedding = get_embedding(query)

    # 5. 计算相似度并排序
    similarities = []
    for item in embeddings:
        similarity = cosine_similarity(query_embedding, item["embedding"])
        similarities.append({
            "index": item["index"],
            "text": item["text"],
            "similarity": similarity
        })

    # 按相似度降序排序
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    # 6. 输出top-3
    print("\n最相似的3个问题:")
    for i, item in enumerate(similarities[:3], 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   问题: {item['text']}")
        print()

if __name__ == "__main__":
    main()