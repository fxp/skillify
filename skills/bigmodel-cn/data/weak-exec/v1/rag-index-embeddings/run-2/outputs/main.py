#!/usr/bin/env python3
import os
import json
import math
import requests

def load_faq_data():
    """加载faq.txt文件，返回问题列表"""
    faq_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    with open(faq_path, 'r', encoding='utf-8') as f:
        questions = [line.strip() for line in f if line.strip()]
    return questions

def get_embedding(text, api_key):
    """使用智谱embedding-3 API获取文本向量"""
    url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "embedding-3",
        "input": text,
        "dimensions": 1024
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    result = response.json()
    # embedding-3 返回的向量在 data[0]['embedding']
    return result['data'][0]['embedding']

def cosine_similarity(vec1, vec2):
    """计算两个向量之间的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 加载faq数据
    questions = load_faq_data()
    print(f"加载了 {len(questions)} 条FAQ")

    # 生成向量
    vectors = []
    for i, question in enumerate(questions):
        print(f"正在处理第 {i+1}/{len(questions)} 条: {question[:30]}...")
        try:
            vector = get_embedding(question, api_key)
            vectors.append({
                "index": i,
                "text": question,
                "vector": vector
            })
        except Exception as e:
            print(f"处理第 {i+1} 条时出错: {e}")

    # 保存到vectors.json
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)

    print(f"已生成 {len(vectors)} 个向量，保存到 vectors.json")

    # 查询"发票怎么开"
    query = "发票怎么开"
    print(f"\n正在查询: {query}")

    try:
        # 获取查询向量
        query_vector = get_embedding(query, api_key)

        # 计算相似度
        similarities = []
        for item in vectors:
            similarity = cosine_similarity(query_vector, item['vector'])
            similarities.append({
                "index": item['index'],
                "text": item['text'],
                "similarity": similarity
            })

        # 按相似度排序，取top-3
        top_3 = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:3]

        # 输出结果
        print(f"\nTop 3 最相似的结果:")
        print("=" * 50)
        for i, item in enumerate(top_3, 1):
            print(f"{i}. 相似度: {item['similarity']:.4f}")
            print(f"   {item['text']}")
            print()

    except Exception as e:
        print(f"查询时出错: {e}")

if __name__ == "__main__":
    main()