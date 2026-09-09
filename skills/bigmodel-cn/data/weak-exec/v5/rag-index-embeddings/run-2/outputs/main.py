import os
import json
import requests
import math

def load_faq(file_path):
    """加载faq文件，每行一个问题"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 去除行号和空格
    questions = []
    for line in lines:
        line = line.strip()
        if line:
            # 去掉行号（假设格式为"数字. 问题"）
            if '.' in line:
                parts = line.split('.', 1)
                if len(parts) > 1 and parts[0].isdigit():
                    question = parts[1].strip()
                    questions.append(question)
                else:
                    questions.append(line)
            else:
                questions.append(line)
    return questions

def get_embedding(text, model="embedding-3", dimensions=1024):
    """获取文本的embedding向量"""
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
    if 'data' not in result or len(result['data']) == 0:
        raise ValueError("获取embedding失败")

    return result['data'][0]['embedding']

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)

def main():
    # 1. 加载FAQ文件（从上级目录的run-1读取）
    faq_file_path = '../run-1/faq.txt'
    faq_questions = load_faq(faq_file_path)
    print(f"加载了 {len(faq_questions)} 个FAQ问题")

    # 2. 获取每个问题的embedding
    print("正在计算FAQ问题的embedding...")
    embeddings = []
    for i, question in enumerate(faq_questions):
        print(f"处理第 {i+1}/{len(faq_questions)} 个问题...")
        try:
            embedding = get_embedding(question)
            embeddings.append({
                "question": question,
                "embedding": embedding
            })
        except Exception as e:
            print(f"处理问题 '{question}' 时出错: {e}")

    # 3. 保存到vectors.json
    with open('vectors.json', 'w', encoding='utf-8') as f:
        json.dump(embeddings, f, ensure_ascii=False, indent=2)
    print("Embeddings已保存到vectors.json")

    # 4. 查询「发票怎么开」
    query = "发票怎么开"
    print(f"\n查询: {query}")

    # 获取查询的embedding
    query_embedding = get_embedding(query)

    # 计算相似度
    similarities = []
    for item in embeddings:
        similarity = cosine_similarity(query_embedding, item['embedding'])
        similarities.append({
            "question": item['question'],
            "similarity": similarity
        })

    # 5. 按相似度排序，取top-3
    top_3 = sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:3]

    # 6. 输出结果到stdout
    print("\n最相关的3个问题：")
    for i, item in enumerate(top_3, 1):
        print(f"{i}. [相似度: {item['similarity']:.4f}] {item['question']}")

if __name__ == "__main__":
    main()