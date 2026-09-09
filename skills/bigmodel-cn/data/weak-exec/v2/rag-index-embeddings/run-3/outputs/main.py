import os
import json
import math
import requests

def load_faq_questions():
    """读取faq.txt文件，每行一个问题"""
    faq_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    with open(faq_path, 'r', encoding='utf-8') as f:
        questions = [line.strip() for line in f if line.strip()]
    return questions

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

    result = response.json()
    # embedding-3 默认返回2048维向量
    return result['data'][0]['embedding']

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have the same length")

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

    # 读取FAQ问题
    print("正在读取FAQ问题...")
    questions = load_faq_questions()
    print(f"读取到 {len(questions)} 个问题")

    # 向量化所有问题
    print("正在向量化所有问题...")
    vectors = []
    for i, question in enumerate(questions):
        print(f"正在处理第 {i+1}/{len(questions)} 个问题...")
        try:
            embedding = get_embedding(question, api_key)
            vectors.append({
                "index": i,
                "question": question,
                "embedding": embedding
            })
        except Exception as e:
            print(f"处理第 {i+1} 个问题时出错: {e}")
            continue

    # 保存向量到JSON文件
    print("正在保存向量到vectors.json...")
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)
    print("向量已保存到 vectors.json")

    # 查询"发票怎么开"
    query = "发票怎么开"
    print(f"\n正在查询: '{query}'")

    # 获取查询向量
    query_embedding = get_embedding(query, api_key)

    # 计算相似度
    similarities = []
    for vec_data in vectors:
        similarity = cosine_similarity(query_embedding, vec_data['embedding'])
        similarities.append({
            "index": vec_data['index'],
            "question": vec_data['question'],
            "similarity": similarity
        })

    # 按相似度排序，取top-3
    top_3 = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:3]

    # 输出结果
    print(f"\nTop 3 最相关的问题:")
    print("=" * 50)
    for i, item in enumerate(top_3, 1):
        print(f"{i}. 相似度: {item['similarity']:.4f}")
        print(f"   问题: {item['question']}")
        print()

if __name__ == "__main__":
    main()