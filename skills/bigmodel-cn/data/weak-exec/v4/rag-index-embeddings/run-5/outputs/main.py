import os
import json
import math
import requests

# API Key 从环境变量读取
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    print("Error: ZHIPUAI_API_KEY environment variable not set")
    exit(1)

# API 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
EMBEDDING_MODEL = "embedding-3"
EMBEDDING_DIM = 1024  # 使用 embedding-3 的 1024 维度

def read_faq_file(file_path):
    """读取 FAQ 文件，返回每行内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines

def get_embeddings(texts):
    """使用智谱 AI embedding-3 模型获取文本向量"""
    url = f"{BASE_URL}/embeddings"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": EMBEDDING_MODEL,
        "input": texts,
        "dimensions": EMBEDDING_DIM
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        # 提取向量数据
        embeddings = []
        for item in result.get("data", []):
            embeddings.append(item.get("embedding", []))

        return embeddings
    except requests.exceptions.RequestException as e:
        print(f"Error calling embeddings API: {e}")
        return None

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        return 0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0

    return dot_product / (magnitude1 * magnitude2)

def search_similar(query_vector, faq_vectors, faq_texts, top_k=3):
    """计算查询向量与 FAQ 向量的相似度，返回最相似的 top_k 个结果"""
    similarities = []

    for i, vector in enumerate(faq_vectors):
        similarity = cosine_similarity(query_vector, vector)
        similarities.append((similarity, i, faq_texts[i]))

    # 按相似度降序排序
    similarities.sort(reverse=True, key=lambda x: x[0])

    return similarities[:top_k]

def main():
    # 1. 读取 FAQ 文件
    faq_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    faq_texts = read_faq_file(faq_file)

    print(f"读取到 {len(faq_texts)} 条 FAQ")

    # 2. 获取所有 FAQ 的向量
    print("正在计算 FAQ 向量...")
    faq_vectors = get_embeddings(faq_texts)

    if faq_vectors is None or len(faq_vectors) != len(faq_texts):
        print("Error: Failed to get embeddings for FAQ texts")
        return

    # 3. 保存向量到文件
    vectors_data = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIM,
        "texts": faq_texts,
        "embeddings": faq_vectors
    }

    with open("/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v4/rag-index-embeddings/run-5/vectors.json", "w", encoding='utf-8') as f:
        json.dump(vectors_data, f, ensure_ascii=False, indent=2)

    print("向量已保存到 vectors.json")

    # 4. 用"发票怎么开"查询
    query = "发票怎么开"
    print(f"\n正在查询: '{query}'")

    # 获取查询向量
    query_vectors = get_embeddings([query])
    if query_vectors is None or len(query_vectors) == 0:
        print("Error: Failed to get embeddings for query")
        return

    query_vector = query_vectors[0]

    # 5. 计算相似度并获取 top-3
    similar_results = search_similar(query_vector, faq_vectors, faq_texts, top_k=3)

    # 6. 打印结果
    print("\n最相关的 3 条 FAQ:")
    print("-" * 50)
    for i, (similarity, index, text) in enumerate(similar_results, 1):
        print(f"{i}. 相似度: {similarity:.4f}")
        print(f"   原文: {text}")
        print()

if __name__ == "__main__":
    main()