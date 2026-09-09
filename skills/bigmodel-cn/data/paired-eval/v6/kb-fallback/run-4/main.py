#!/usr/bin/env python3
"""
智谱AI知识库检索示例
1. 创建知识库并上传faq.txt
2. 检索"退换货政策的有效期是多久"
3. 打印检索到的原文片段
4. 如果知识库不可用，使用embeddings替代方案
"""

import os
import requests
import time
import json
from typing import List, Dict, Optional

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 检查API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

faq_file_path = "../run-3/faq.txt"

def handle_api_error(resp: requests.Response) -> bool:
    """处理API错误，返回True表示成功"""
    try:
        data = resp.json()
        if data.get("code") == 200:
            return True
        print(f"API错误: {data}")
        return False
    except:
        print(f"HTTP错误: {resp.status_code}")
        return False

def create_knowledge_base() -> Optional[str]:
    """创建知识库"""
    print("正在创建知识库...")
    url = f"{BASE_URL}/llm-application/open/knowledge"
    data = {
        "embedding_id": 11,  # Embedding-3
        "name": "退换货政策知识库",
        "description": "退换货政策相关文档"
    }

    resp = requests.post(url, headers=headers, json=data)
    if handle_api_error(resp):
        result = resp.json()
        knowledge_id = result["data"]["id"]
        print(f"✓ 知识库创建成功，ID: {knowledge_id}")
        return knowledge_id
    else:
        return None

def upload_document(knowledge_id: str) -> Optional[str]:
    """上传文档到知识库"""
    print("正在上传文档...")
    url = f"{BASE_URL}/llm-application/open/document/upload_document/{knowledge_id}"

    with open(faq_file_path, "rb") as f:
        files = {"files": f}
        data = {
            "knowledge_type": 1,  # 按标题段落切
            "parse_image": "false"
        }

        resp = requests.post(url, headers=headers, files=files, data=data)

    if handle_api_error(resp):
        result = resp.json()
        if result["data"]["successInfos"]:
            document_id = result["data"]["successInfos"][0]["documentId"]
            print(f"✓ 文档上传成功，ID: {document_id}")
            return document_id
    return None

def wait_embedding_complete(document_id: str, timeout: int = 300) -> bool:
    """等待文档向量化完成"""
    print("等待向量化完成...")
    url = f"{BASE_URL}/llm-application/open/document/{document_id}"

    start_time = time.time()
    while time.time() - start_time < timeout:
        resp = requests.get(url, headers=headers)
        if handle_api_error(resp):
            data = resp.json()
            embedding_stat = data["data"]["embedding_stat"]
            if embedding_stat == 1:
                print("✓ 向量化完成")
                return True
            elif embedding_stat == 2:
                print(f"✗ 向量化失败: {data['data']['failInfo']}")
                return False
        time.sleep(5)

    print("✗ 向量化超时")
    return False

def retrieve_knowledge(knowledge_id: str, query: str = "退换货政策的有效期是多久") -> Optional[List[Dict]]:
    """从知识库检索内容"""
    print(f"正在检索: {query}")
    url = f"{BASE_URL}/llm-application/open/knowledge/retrieve"

    data = {
        "query": query,
        "knowledge_ids": [knowledge_id],
        "top_k": 5,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    resp = requests.post(url, headers=headers, json=data)
    if handle_api_error(resp):
        result = resp.json()
        if result["data"]:
            print(f"✓ 检索到 {len(result['data'])} 条结果")
            return result["data"]
    return None

def print_retrieved_results(results: List[Dict]):
    """打印检索结果"""
    print("\n=== 检索到的原文片段 ===")
    for i, item in enumerate(results, 1):
        print(f"\n片段 {i}:")
        print(f"内容: {item['text']}")
        print(f"相似度: {item['score']:.2f}")
        if item['metadata'].get('doc_name'):
            print(f"来源: {item['metadata']['doc_name']}")

def embeddings_fallback_search(query: str) -> Optional[List[Dict]]:
    """使用embeddings作为替代方案"""
    print("\n=== 使用embeddings替代方案 ===")

    # 1. 获取查询的embedding
    print("正在获取查询向量...")
    embed_url = f"{BASE_URL}/paas/v4/embeddings"
    embed_data = {
        "model": "embedding-3",
        "input": [query]
    }

    resp = requests.post(embed_url, headers=headers, json=embed_data)
    if resp.status_code != 200:
        print("✗ 获取embedding失败")
        return None

    embed_result = resp.json()
    query_embedding = embed_result["data"][0]["embedding"]

    # 2. 读取faq内容并获取所有段落embedding
    with open(faq_file_path, "r", encoding="utf-8") as f:
        faq_content = f.read()

    # 按段落分割
    paragraphs = []
    lines = faq_content.split('\n')
    current_paragraph = ""

    for line in lines:
        if line.strip() and not line.startswith(('1.', '2.', '3.', '4.', '5.')):
            if current_paragraph:
                paragraphs.append(current_paragraph.strip())
            current_paragraph = line
        else:
            if current_paragraph:
                paragraphs.append(current_paragraph.strip())
                current_paragraph = line

    if current_paragraph:
        paragraphs.append(current_paragraph.strip())

    # 过滤空段落
    paragraphs = [p for p in paragraphs if p.strip()]

    print(f"正在为 {len(paragraphs)} 个段落生成向量...")
    # 分批处理embedding
    batch_size = 64
    all_embeddings = []

    for i in range(0, len(paragraphs), batch_size):
        batch = paragraphs[i:i+batch_size]
        batch_data = {
            "model": "embedding-3",
            "input": batch
        }

        resp = requests.post(embed_url, headers=headers, json=batch_data)
        if resp.status_code == 200:
            batch_result = resp.json()
            batch_embeddings = [item["embedding"] for item in batch_result["data"]]
            all_embeddings.extend(batch_embeddings)
        else:
            print(f"✗ 第 {i//batch_size+1} 批embedding失败")
            return None

    # 3. 计算相似度（简化版，实际应该用更精确的cosine similarity）
    similarities = []
    for i, (para, emb) in enumerate(zip(paragraphs, all_embeddings)):
        # 简化的相似度计算（点积）
        sim = sum(q * e for q, e in zip(query_embedding, emb))
        similarities.append((i, sim, para))

    # 4. 按相似度排序并返回前5个
    similarities.sort(key=lambda x: x[1], reverse=True)

    results = []
    for i, idx, score in similarities[:5]:
        results.append({
            "text": paragraphs[idx],
            "score": score,
            "metadata": {"doc_name": "faq.txt"}
        })

    print("✓ embeddings检索完成")
    return results

def cleanup_resources(knowledge_id: Optional[str], document_id: Optional[str]):
    """清理临时资源"""
    print("\n正在清理资源...")
    try:
        # 删除文档
        if document_id:
            url = f"{BASE_URL}/llm-application/open/document/{document_id}"
            requests.delete(url, headers=headers)
            print("✓ 文档已删除")

        # 删除知识库
        if knowledge_id:
            url = f"{BASE_URL}/llm-application/open/knowledge/{knowledge_id}"
            requests.delete(url, headers=headers)
            print("✓ 知识库已删除")
    except Exception as e:
        print(f"清理时出现错误: {e}")

def main():
    print("=== 智谱AI知识库检索示例 ===\n")

    knowledge_id = None
    document_id = None

    try:
        # 步骤1: 创建知识库
        knowledge_id = create_knowledge_base()
        if not knowledge_id:
            print("✗ 知识库创建失败，使用embeddings替代方案")
            embeddings_results = embeddings_fallback_search("退换货政策的有效期是多久")
            if embeddings_results:
                print_retrieved_results(embeddings_results)
            else:
                print("✗ 替代方案也失败了")
            return

        # 步骤2: 上传文档
        document_id = upload_document(knowledge_id)
        if not document_id:
            print("✗ 文档上传失败，使用embeddings替代方案")
            embeddings_results = embeddings_fallback_search("退换货政策的有效期是多久")
            if embeddings_results:
                print_retrieved_results(embeddings_results)
            else:
                print("✗ 替代方案也失败了")
            return

        # 步骤3: 等待向量化完成
        if not wait_embedding_complete(document_id):
            print("✗ 向量化失败，使用embeddings替代方案")
            embeddings_results = embeddings_fallback_search("退换货政策的有效期是多久")
            if embeddings_results:
                print_retrieved_results(embeddings_results)
            else:
                print("✗ 替代方案也失败了")
            return

        # 步骤4: 检询
        results = retrieve_knowledge(knowledge_id, "退换货政策的有效期是多久")
        if results:
            print_retrieved_results(results)
        else:
            print("✗ 知识库检索失败，使用embeddings替代方案")
            embeddings_results = embeddings_fallback_search("退换货政策的有效期是多久")
            if embeddings_results:
                print_retrieved_results(embeddings_results)
            else:
                print("✗ 替代方案也失败了")

    finally:
        # 清理资源
        cleanup_resources(knowledge_id, document_id)

if __name__ == "__main__":
    main()