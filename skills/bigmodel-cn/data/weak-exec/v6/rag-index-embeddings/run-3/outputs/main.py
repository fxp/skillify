#!/usr/bin/env python3
import os
import json
import requests
import math
import re

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
EMBEDDING_MODEL = "embedding-3"
EMBEDDING_BATCH_SIZE = 64  # 单次最多处理64条
EMBEDDING_DIM = 1024  # 使用较小的维度以提高效率

def load_faq_data():
    """加载FAQ数据"""
    with open("faq.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines

def get_embedding(texts, model=EMBEDDING_MODEL):
    """获取文本向量"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    all_embeddings = []
    total_texts = len(texts)

    for i in range(0, total_texts, EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        data = {
            "model": model,
            "input": batch,
            "dimensions": EMBEDDING_DIM
        }

        try:
            response = requests.post(
                f"{BASE_URL}/embeddings",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if "data" not in result:
                raise ValueError(f"API返回格式错误: {result}")

            batch_embeddings = [item["embedding"] for item in result["data"]]
            all_embeddings.extend(batch_embeddings)

            print(f"已处理 {min(i + EMBEDDING_BATCH_SIZE, total_texts)}/{total_texts} 条文本...")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"请求失败: {e}")
        except ValueError as e:
            raise ValueError(f"数据解析错误: {e}")

    if len(all_embeddings) != total_texts:
        raise RuntimeError(f"向量数量不匹配，期望{total_texts}个，得到{len(all_embeddings)}个")

    return all_embeddings

def cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    # 计算点积
    dot_product = sum(a * b for a, b in zip(vec1, vec2))

    # 计算向量的模长
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    # 避免除以0
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def save_vectors(vectors, faqs):
    """保存向量数据到JSON文件"""
    data = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIM,
        "total": len(faqs),
        "vectors": [
            {
                "index": i,
                "text": faqs[i],
                "vector": vectors[i]
            }
            for i in range(len(faqs))
        ]
    }

    with open("vectors.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"向量数据已保存到 vectors.json，共 {len(faqs)} 条")

def find_most_similar(query_vector, faq_vectors, faqs, top_k=3):
    """查找最相似的FAQ"""
    similarities = []

    for i, (vector, text) in enumerate(zip(faq_vectors, faqs)):
        similarity = cosine_similarity(query_vector, vector)
        similarities.append((similarity, i, text))

    # 按相似度降序排序
    similarities.sort(reverse=True, key=lambda x: x[0])

    # 返回前top_k个结果
    return similarities[:top_k]

def main():
    print("开始处理FAQ数据...")

    # 1. 加载FAQ数据
    faqs = load_faq_data()
    print(f"加载了 {len(faqs)} 条FAQ")

    # 2. 生成向量
    print("开始生成向量...")
    faq_vectors = get_embedding(faqs)

    # 3. 保存向量数据
    save_vectors(faq_vectors, faqs)

    # 4. 查询
    query = "发票怎么开"
    print(f"\n开始查询: '{query}'")

    # 5. 对查询文本进行向量化
    query_vectors = get_embedding([query])
    query_vector = query_vectors[0]

    # 6. 计算相似度并找最相似的结果
    top_3 = find_most_similar(query_vector, faq_vectors, faqs, 3)

    # 7. 输出结果
    print("\n最相关的3条FAQ:")
    print("-" * 50)
    for i, (similarity, idx, text) in enumerate(top_3, 1):
        print(f"{i}. 相似度: {similarity:.4f}")
        print(f"   问题: {text}")
        print()

if __name__ == "__main__":
    if not API_KEY:
        print("错误: 请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    try:
        main()
    except Exception as e:
        print(f"错误: {e}")
        exit(1)