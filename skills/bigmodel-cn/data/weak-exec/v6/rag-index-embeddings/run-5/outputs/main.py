#!/usr/bin/env python3
import os
import json
import math
import requests


def load_faq(file_path):
    """加载FAQ文件，返回每行内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


def embed_text(text, model="embedding-3", dimensions=2048):
    """调用智谱API获取文本的embedding向量"""
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
        "input": text,
        "dimensions": dimensions
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()
    if "data" not in result:
        raise RuntimeError(f"API返回异常：{result}")

    return result["data"][0]["embedding"]


def cosine_similarity(a, b):
    """计算两个向量的余弦相似度"""
    if len(a) != len(b):
        raise ValueError("向量维度不一致")

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def main():
    # 文件路径
    faq_file = "../faq.txt"
    output_file = "vectors.json"

    # 1. 加载FAQ内容
    print("正在加载FAQ文件...")
    faq_lines = load_faq(faq_file)
    print(f"共加载 {len(faq_lines)} 条FAQ")

    # 2. 向量化每一条FAQ
    print("正在向量化FAQ...")
    vectors = []

    for i, text in enumerate(faq_lines):
        print(f"正在处理第 {i+1}/{len(faq_lines)} 条...")
        try:
            embedding = embed_text(text)
            vectors.append({
                "index": i,
                "text": text,
                "vector": embedding
            })
        except Exception as e:
            print(f"处理第 {i+1} 条时出错: {e}")
            continue

    # 3. 保存向量到JSON文件
    print(f"正在保存向量到 {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)

    # 4. 用"发票怎么开"进行查询
    query_text = "发票怎么开"
    print(f"\n正在查询: '{query_text}'")

    # 获取查询文本的embedding
    query_vector = embed_text(query_text)

    # 计算与所有FAQ的相似度
    similarities = []
    for item in vectors:
        sim = cosine_similarity(query_vector, item["vector"])
        similarities.append({
            "index": item["index"],
            "text": item["text"],
            "similarity": sim
        })

    # 按相似度降序排序
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    # 输出top-3最相似的结果
    print("\nTop 3 最相似的结果:")
    print("=" * 50)
    for i, item in enumerate(similarities[:3]):
        print(f"{i+1}. 相似度: {item['similarity']:.4f}")
        print(f"   原文: {item['text']}")
        print()


if __name__ == "__main__":
    main()