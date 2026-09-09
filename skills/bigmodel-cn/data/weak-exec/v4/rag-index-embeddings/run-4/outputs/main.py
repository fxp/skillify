#!/usr/bin/env python3
import os
import json
import math
import requests

def load_faq_lines():
    """读取faq.txt文件，返回每行内容列表"""
    faq_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/v4/rag-index-embeddings/run-3/faq.txt"
    with open(faq_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines

def get_embedding(text):
    """使用embedding-3模型获取文本向量"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "embedding-3",
        "input": text,
        "dimensions": 1024  # 使用1024维度，与embedding-3兼容
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    result = response.json()
    return result['data'][0]['embedding']

def cosine_similarity(a, b):
    """计算两个向量的余弦相似度"""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0
    return dot_product / (norm_a * norm_b)

def main():
    try:
        # 1. 加载FAQ数据
        print("正在加载FAQ数据...")
        faq_lines = load_faq_lines()
        print(f"加载了 {len(faq_lines)} 条FAQ")

        # 2. 向量化所有FAQ
        print("正在向量化FAQ...")
        vectors = []
        for i, line in enumerate(faq_lines):
            print(f"正在处理第 {i+1}/{len(faq_lines)} 条...")
            embedding = get_embedding(line)
            vectors.append({
                "index": i,
                "text": line,
                "vector": embedding
            })

        # 3. 保存向量到JSON文件
        print("正在保存向量数据...")
        with open("vectors.json", "w", encoding='utf-8') as f:
            json.dump(vectors, f, ensure_ascii=False, indent=2)
        print("向量数据已保存到 vectors.json")

        # 4. 查询"发票怎么开"
        print("\n正在查询'发票怎么开'...")
        query_embedding = get_embedding("发票怎么开")

        # 5. 计算相似度并排序
        similarities = []
        for item in vectors:
            sim = cosine_similarity(query_embedding, item['vector'])
            similarities.append({
                "index": item['index'],
                "text": item['text'],
                "similarity": sim
            })

        # 按相似度降序排序
        similarities.sort(key=lambda x: x['similarity'], reverse=True)

        # 6. 输出top-3结果
        print("\n最相关的3条结果：")
        for i, item in enumerate(similarities[:3], 1):
            print(f"{i}. 相似度: {item['similarity']:.4f}")
            print(f"   原文: {item['text']}\n")

    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()