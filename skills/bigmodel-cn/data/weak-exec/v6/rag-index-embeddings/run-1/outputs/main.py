import os
import json
import math
import requests

def load_faq(file_path):
    """加载FAQ文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 去掉每行的数字前缀和空格
    faqs = []
    for line in lines:
        line = line.strip()
        # 跳过空行
        if line:
            # 去掉数字前缀（如果有）
            if line[0].isdigit():
                # 找到第一个非数字字符的位置
                i = 0
                while i < len(line) and line[i].isdigit():
                    i += 1
                while i < len(line) and line[i] == ' ':
                    i += 1
                if i < len(line):
                    line = line[i:]
                else:
                    line = ""
            if line:
                faqs.append(line)
    return faqs

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
    if "data" not in result:
        raise RuntimeError(f"API调用失败: {result}")

    return result["data"][0]["embedding"]

def cosine_similarity(vec1, vec2):
    """计算两个向量的余弦相似度"""
    if len(vec1) != len(vec2):
        raise ValueError("向量维度不一致")

    dot_product = 0
    norm1 = 0
    norm2 = 0

    for i in range(len(vec1)):
        dot_product += vec1[i] * vec2[i]
        norm1 += vec1[i] ** 2
        norm2 += vec2[i] ** 2

    if norm1 == 0 or norm2 == 0:
        return 0

    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))

def main():
    # 文件路径
    faq_file = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/weak-exec/faq.txt"
    output_file = "vectors.json"

    # 加载FAQ
    print("加载FAQ文件...")
    faqs = load_faq(faq_file)
    print(f"加载了 {len(faqs)} 条FAQ")

    # 获取所有FAQ的embedding
    print("生成FAQ的向量表示...")
    embeddings = []

    for i, text in enumerate(faqs):
        print(f"正在处理第 {i+1}/{len(faqs)} 条: {text[:20]}...")
        try:
            embedding = get_embedding(text)
            embeddings.append({
                "text": text,
                "embedding": embedding
            })
        except Exception as e:
            print(f"处理第 {i+1} 条时出错: {e}")
            continue

    # 保存到文件
    print(f"保存向量数据到 {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(embeddings, f, ensure_ascii=False, indent=2)

    # 查询问题
    query = "发票怎么开"
    print(f"\n查询问题: '{query}'")

    # 获取查询的embedding
    query_embedding = get_embedding(query)

    # 计算相似度
    similarities = []
    for item in embeddings:
        similarity = cosine_similarity(query_embedding, item["embedding"])
        similarities.append({
            "text": item["text"],
            "similarity": similarity
        })

    # 排序并取top-3
    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    top_3 = similarities[:3]

    # 打印结果
    print("\n最相关的3条FAQ:")
    for i, item in enumerate(top_3, 1):
        print(f"{i}. [相似度: {item['similarity']:.4f}] {item['text']}")

if __name__ == "__main__":
    main()