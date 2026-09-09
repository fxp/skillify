#!/usr/bin/env python3
import os
import json
import math
import requests

# 从环境变量读取 API Key
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# API 配置
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
EMBEDDING_MODEL = "embedding-3"
EMBEDDING_DIM = 1024  # 使用 embedding-3 的 1024 维度

# 读取 faq.txt 文件
def read_faq_file():
    faq_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            questions = [line.strip() for line in f if line.strip()]
        print(f"成功读取了 {len(questions)} 条 FAQ")
        return questions
    except FileNotFoundError:
        print(f"错误：找不到文件 {faq_path}")
        exit(1)
    except Exception as e:
        print(f"读取文件时出错：{e}")
        exit(1)

# 获取文本向量
def get_embeddings(texts):
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
        vectors = []
        for item in result['data']:
            vectors.append(item['embedding'])

        print(f"成功向化了 {len(texts)} 条文本")
        return vectors
    except requests.exceptions.RequestException as e:
        print(f"API 请求失败：{e}")
        exit(1)
    except KeyError:
        print("错误：API 响应格式不正确")
        exit(1)

# 计算余弦相似度
def cosine_similarity(vec_a, vec_b):
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0

    return dot_product / (magnitude_a * magnitude_b)

# 查询最相似的问题
def search_similar(query_vector, faq_questions, faq_vectors, top_k=3):
    similarities = []

    for i, vector in enumerate(faq_vectors):
        similarity = cosine_similarity(query_vector, vector)
        similarities.append((similarity, i))

    # 按相似度降序排序
    similarities.sort(reverse=True, key=lambda x: x[0])

    # 返回 top-k 结果
    return similarities[:top_k]

def main():
    print("开始构建 FAQ 向量库...")

    # 1. 读取 FAQ 文件
    faq_questions = read_faq_file()

    # 2. 向量化所有问题
    faq_vectors = get_embeddings(faq_questions)

    # 3. 保存向量数据到文件
    vector_data = {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIM,
        "total_questions": len(faq_questions),
        "vectors": []
    }

    for i, (question, vector) in enumerate(zip(faq_questions, faq_vectors)):
        vector_data["vectors"].append({
            "index": i,
            "question": question,
            "vector": vector
        })

    # 保存到 vectors.json
    with open("vectors.json", "w", encoding="utf-8") as f:
        json.dump(vector_data, f, ensure_ascii=False, indent=2)

    print("向量数据已保存到 vectors.json")

    # 4. 查询示例："发票怎么开"
    print("\n查询示例：发票怎么开")
    query_text = "发票怎么开"
    query_vector = get_embeddings([query_text])[0]

    # 5. 搜索最相似的问题
    similar_results = search_similar(query_vector, faq_questions, faq_vectors, top_k=3)

    # 6. 输出结果
    print("\n最相似的 3 个问题：")
    for rank, (similarity, index) in enumerate(similar_results, 1):
        print(f"{rank}. 相似度: {similarity:.4f}")
        print(f"   问题: {faq_questions[index]}")
        print()

if __name__ == "__main__":
    main()