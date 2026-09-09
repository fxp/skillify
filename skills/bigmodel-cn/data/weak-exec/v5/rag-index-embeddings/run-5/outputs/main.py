import os
import json
import requests
import math

def load_faq():
    """加载FAQ文件，返回每行内容"""
    with open("faq.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()
    # 去除每行的换行符和空白字符
    return [line.strip() for line in lines if line.strip()]

def get_embeddings(texts, model="embedding-3"):
    """使用智谱AI的embedding模型获取文本向量"""
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 分批处理，embedding-3 每次最多处理64条
    batch_size = 64
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        data = {
            "model": model,
            "input": batch_texts
        }

        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        # 检查响应是否包含embeddings
        if "data" not in result:
            raise RuntimeError(f"API响应错误: {result}")

        # 添加当前批次的embeddings
        for item in result["data"]:
            if "embedding" not in item:
                raise RuntimeError(f"Embedding数据缺失: {item}")
            all_embeddings.append(item["embedding"])

    return all_embeddings

def calculate_cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    # 计算点积
    dot_product = sum(a * b for a, b in zip(vec1, vec2))

    # 计算向量模长
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    # 避免除以0
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def save_embeddings(faq_texts, embeddings):
    """保存FAQ文本和向量到json文件"""
    data = {
        "faq_texts": faq_texts,
        "embeddings": embeddings,
        "model": "embedding-3"
    }

    with open("vectors.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    print("正在加载FAQ数据...")
    faq_texts = load_faq()
    print(f"加载了 {len(faq_texts)} 条FAQ")

    print("正在生成向量...")
    embeddings = get_embeddings(faq_texts)
    print(f"生成了 {len(embeddings)} 个向量")

    print("正在保存向量数据...")
    save_embeddings(faq_texts, embeddings)
    print("向量数据已保存到 vectors.json")

    # 使用「发票怎么开」进行查询
    query = "发票怎么开"
    print(f"\n正在查询: '{query}'")

    # 获取查询向量化
    print("正在查询向量化...")
    query_embeddings = get_embeddings([query])
    query_vector = query_embeddings[0]

    # 计算余弦相似度
    similarities = []
    for i, (text, vector) in enumerate(zip(faq_texts, embeddings)):
        similarity = calculate_cosine_similarity(query_vector, vector)
        similarities.append((similarity, i, text))

    # 按相似度降序排序
    similarities.sort(reverse=True, key=lambda x: x[0])

    # 获取top 3
    top_3 = similarities[:3]

    print("\n最相关的3条结果:")
    print("-" * 50)
    for i, (similarity, idx, text) in enumerate(top_3, 1):
        print(f"{i}. 相似度: {similarity:.4f}")
        print(f"   原文: {text}")
        print()

if __name__ == "__main__":
    main()