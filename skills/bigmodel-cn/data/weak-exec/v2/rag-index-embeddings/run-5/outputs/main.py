#!/usr/bin/env python3
import os
import json
import math
import requests

def load_faq(file_path):
    """加载FAQ文件，每行一条问题"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_embedding(text, api_key):
    """使用智谱embedding-3模型获取文本向量"""
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
    return response.json()

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0

    return dot_product / (magnitude1 * magnitude2)

def main():
    # 从环境变量读取API Key
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    # 加载FAQ
    faq_file = "../faq.txt"
    faqs = load_faq(faq_file)
    print(f"加载了 {len(faqs)} 条FAQ")

    # 对每条FAQ进行向量化
    print("开始向量化FAQ...")
    embeddings_data = []

    # 分批处理，避免请求过大
    batch_size = 10
    for i in range(0, len(faqs), batch_size):
        batch = faqs[i:i + batch_size]
        print(f"处理批次 {i//batch_size + 1}: {i+1}-{min(i+len(batch), len(faqs))}")

        try:
            result = get_embedding(batch, api_key)

            # 提取向量数据
            for item in result['data']:
                embeddings_data.append({
                    'index': item['index'],
                    'text': faqs[item['index']],  # 确保索引对应
                    'embedding': item['embedding']
                })

        except Exception as e:
            print(f"批次 {i//batch_size + 1} 处理失败: {e}")
            continue

    # 保存向量数据
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(embeddings_data, f, ensure_ascii=False, indent=2)

    print(f"向量已保存到 vectors.json，共 {len(embeddings_data)} 条")

    # 查询相似问题
    query = "发票怎么开"
    print(f"\n查询: {query}")

    # 获取查询向量
    print("计算查询向量...")
    query_result = get_embedding([query], api_key)
    query_embedding = query_result['data'][0]['embedding']

    # 计算相似度
    similarities = []
    for item in embeddings_data:
        sim = cosine_similarity(query_embedding, item['embedding'])
        similarities.append({
            'text': item['text'],
            'similarity': sim
        })

    # 按相似度排序并取top-3
    top_3 = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:3]

    # 输出结果
    print("\n最相似的3条问题:")
    for i, item in enumerate(top_3, 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   问题: {item['text']}")
        print()

if __name__ == "__main__":
    main()