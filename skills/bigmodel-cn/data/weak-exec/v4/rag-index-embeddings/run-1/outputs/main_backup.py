#!/usr/bin/env python3
import os
import requests
import json
import math

def get_embedding(text):
    """获取文本的embedding向量"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        exit(1)

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()

        if "data" not in result or len(result["data"]) == 0:
            print(f"错误：API返回数据异常: {result}")
            return None

        return result["data"][0]["embedding"]

    except requests.exceptions.RequestException as e:
        print(f"API请求错误: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON解析错误: {e}")
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

def main():
    faq_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"

    try:
        with open(faq_file, 'r', encoding='utf-8') as f:
            questions = [line.strip() for line in f if line.strip()]

        print(f"读取到 {len(questions)} 条常见问题")

        embeddings = []
        for i, question in enumerate(questions):
            print(f"正在处理第 {i+1}/{len(questions)} 条...")
            embedding = get_embedding(question)
            if embedding is not None:
                embeddings.append({
                    "index": i,
                    "question": question,
                    "embedding": embedding
                })
            else:
                print(f"跳过第 {i+1} 条问题")

        if not embeddings:
            print("错误：没有成功获取任何embedding")
            return

        with open('vectors.json', 'w', encoding='utf-8') as f:
            json.dump(embeddings, f, ensure_ascii=False, indent=2)

        print(f"成功保存 {len(embeddings)} 条向量到 vectors.json")

        query = "发票怎么开"
        print(f"\n查询文本: '{query}'")

        query_embedding = get_embedding(query)
        if query_embedding is None:
            print("错误：无法获取查询文本的embedding")
            return

        similarities = []
        for item in embeddings:
            similarity = cosine_similarity(query_embedding, item["embedding"])
            similarities.append({
                "index": item["index"],
                "question": item["question"],
                "similarity": similarity
            })

        similarities.sort(key=lambda x: x["similarity"], reverse=True)

        top_3 = similarities[:3]

        print("\n最相关的3条内容:")
        print("-" * 50)
        for i, item in enumerate(top_3, 1):
            print(f"{i}. [相似度: {item['similarity']:.4f}]")
            print(f"   {item['question']}")
            print()

if __name__ == "__main__":
    main()
