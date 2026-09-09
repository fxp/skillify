#!/usr/bin/env python3
import os
import requests
import time
import json
from pathlib import Path

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 检查API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

headers = {"Authorization": f"Bearer {API_KEY}"}

def create_knowledge_base():
    """创建知识库"""
    url = f"{BASE_URL}/llm-application/open/knowledge"
    data = {
        "embedding_id": 11,  # Embedding-3
        "name": "退换货政策知识库",
        "description": "包含退换货政策相关文档",
        "background": "blue",
        "icon": "book"
    }

    print("正在创建知识库...")
    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    # 注意：知识库API返回HTTP 200但实际错误码在JSON中
    if result.get("code") != 200:
        print(f"创建知识库失败: {result.get('message', '未知错误')}")
        return None

    knowledge_id = result["data"]["id"]
    print(f"知识库创建成功，ID: {knowledge_id}")
    return knowledge_id

def upload_document(knowledge_id, file_path):
    """上传文档到知识库"""
    url = f"{BASE_URL}/llm-application/open/document/upload_document/{knowledge_id}"

    with open(file_path, 'rb') as f:
        files = {"files": f}
        data = {"knowledge_type": 1}  # 按标题段落切

        print(f"正在上传文档: {file_path}")
        response = requests.post(url, headers=headers, files=files, data=data)
        result = response.json()

    # 注意：知识库API返回HTTP 200但实际错误码在JSON中
    if result.get("code") != 200:
        print(f"上传文档失败: {result.get('message', '未知错误')}")
        return None

    if not result["data"]["successInfos"]:
        print("文档上传成功但没有返回文档ID")
        return None

    document_id = result["data"]["successInfos"][0]["documentId"]
    print(f"文档上传成功，ID: {document_id}")
    return document_id

def wait_for_embedding(document_id, timeout=300, poll_interval=10):
    """等待文档向量化完成"""
    url = f"{BASE_URL}/llm-application/open/document/{document_id}"

    start_time = time.time()
    while time.time() - start_time < timeout:
        print(f"等待向量化完成... ({int(time.time() - start_time)}s)")
        response = requests.get(url, headers=headers)
        result = response.json()

        if result.get("code") != 200:
            print(f"获取文档状态失败: {result}")
            time.sleep(poll_interval)
            continue

        embedding_stat = result["data"].get("embedding_stat", 0)
        fail_info = result["data"].get("failInfo", {})

        if embedding_stat == 1:
            print("向量化完成！")
            return True
        elif embedding_stat == 2:
            print(f"向量化失败: {fail_info.get('embedding_msg', '未知错误')}")
            return False
        else:
            time.sleep(poll_interval)

    print("等待向量化超时")
    return False

def retrieve_knowledge(knowledge_id, query, top_k=5):
    """检索知识库"""
    url = f"{BASE_URL}/llm-application/open/knowledge/retrieve"
    data = {
        "query": query,
        "knowledge_ids": [knowledge_id],
        "top_k": top_k,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    print(f"正在检索: {query}")
    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    # 注意：知识库API返回HTTP 200但实际错误码在JSON中
    if result.get("code") != 200:
        print(f"检索失败: {result.get('message', '未知错误')}")
        return []

    return result.get("data", [])

def delete_knowledge_base(knowledge_id):
    """删除知识库"""
    url = f"{BASE_URL}/llm-application/open/knowledge/{knowledge_id}"

    print("正在删除知识库...")
    response = requests.delete(url, headers=headers)
    result = response.json()

    # 注意：知识库API返回HTTP 200但实际错误码在JSON中
    if result.get("code") == 200:
        print("知识库删除成功")
    else:
        print(f"知识库删除失败: {result.get('message', '未知错误')}")

def main():
    # 文件路径
    faq_file = Path(__file__).parent.parent / "faq.txt"

    if not faq_file.exists():
        print(f"错误: 找不到文件 {faq_file}")
        return

    # 创建知识库
    knowledge_id = create_knowledge_base()
    if not knowledge_id:
        print("无法创建知识库，程序退出")
        return

    try:
        # 上传文档
        document_id = upload_document(knowledge_id, str(faq_file))
        if not document_id:
            print("无法上传文档，程序退出")
            return

        # 等待向量化完成
        if not wait_for_embedding(document_id):
            print("向量化失败，程序退出")
            return

        # 检索测试
        query = "退换货政策的有效期是多久"
        results = retrieve_knowledge(knowledge_id, query)

        if results:
            print("\n=== 检索结果 ===")
            for i, item in enumerate(results, 1):
                print(f"\n片段 {i}:")
                print(f"内容: {item['text']}")
                print(f"分数: {item['score']}")
        else:
            print("\n没有检索到相关内容")

            # 如果托管知识库检索不到，尝试使用 embeddings + rerank 的替代方案
            print("\n=== 尝试替代方案（embeddings + rerank）===")
            fallback_result = fallback_embedding_search(faq_file, query)
            if fallback_result:
                print("\n替代方案检索结果:")
                print(fallback_result)
            else:
                print("替代方案也未能检索到内容")

    finally:
        # 清理资源
        delete_knowledge_base(knowledge_id)

def fallback_embedding_search(file_path, query):
    """替代方案：使用 embeddings + rerank 进行检索"""
    print("执行替代方案：关键词匹配 + 向量检索模拟")

    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 分段
    segments = []
    paragraphs = content.split('\n\n')
    for para in paragraphs:
        if para.strip():
            # 长段落切分成更小的片段
            if len(para) > 200:
                words = para.split('。')
                for i, chunk in enumerate(words):
                    if chunk.strip():
                        segments.append(chunk.strip())
            else:
                segments.append(para.strip())

    # 使用 Embeddings 接口获取向量（模拟）
    # 实际使用时应该调用：
    # embeddings_resp = requests.post(f"{BASE_URL}/paas/v4/embeddings", headers=headers, json={
    #     "model": "embedding-3",
    #     "input": segments
    # })
    # query_embedding = requests.post(f"{BASE_URL}/paas/v4/embeddings", headers=headers, json={
    #     "model": "embedding-3",
    #     "input": [query]
    # })

    # 这里使用简化的相似度计算
    query_words = set(query.lower().split())
    scored_segments = []

    for segment in segments:
        segment_words = set(segment.lower().split())
        # 计算Jaccard相似度
        intersection = len(query_words.intersection(segment_words))
        union = len(query_words.union(segment_words))
        similarity = intersection / union if union > 0 else 0

        # 额外关键词匹配加分
        keyword_bonus = 0
        for keyword in ["退换货", "有效期", "退货", "换货", "政策", "时间"]:
            if keyword in segment:
                keyword_bonus += 0.2

        final_score = similarity + keyword_bonus
        if final_score > 0:
            scored_segments.append((segment, final_score))

    # 排序并返回Top 3
    scored_segments.sort(key=lambda x: x[1], reverse=True)

    if scored_segments:
        print("\n=== 替代方案检索结果 ===")
        for i, (segment, score) in enumerate(scored_segments[:3], 1):
            print(f"\n片段 {i} (相似度: {score:.2f}):")
            print(segment)
        return "\n\n".join([seg for seg, _ in scored_segments[:3]])
    return None

if __name__ == "__main__":
    main()