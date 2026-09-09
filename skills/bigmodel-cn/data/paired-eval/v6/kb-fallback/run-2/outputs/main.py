#!/usr/bin/env python3
"""
智谱AI知识库检索示例
1. 创建托管知识库并上传文档
2. 检索"退换货政策的有效期是多久"
3. 如果托管知识库不可用，使用embeddings + rerank替代方案
"""

import os
import json
import time
import requests
from typing import List, Dict, Optional

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def wait_for_embedding_completion(document_id: str, timeout: int = 300, poll_interval: int = 5) -> bool:
    """等待文档向量化完成"""
    print(f"等待文档向量化完成... (文档ID: {document_id})")

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = requests.get(
                f"{BASE_URL}/llm-application/open/document/{document_id}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 200:
                print(f"错误: {data}")
                return False

            embedding_stat = data.get("data", {}).get("embedding_stat")
            if embedding_stat == 1:
                print("文档向量化完成！")
                return True
            elif embedding_stat == 2:
                fail_info = data.get("data", {}).get("failInfo", {})
                print(f"文档向量化失败: {fail_info}")
                return False
            else:
                print(f"处理中... 状态: {embedding_stat}")
                time.sleep(poll_interval)

        except Exception as e:
            print(f"检查状态时出错: {e}")
            time.sleep(poll_interval)

    print("超时：等待文档向量化完成")
    return False

def create_knowledge_base() -> Optional[str]:
    """创建知识库"""
    print("正在创建知识库...")

    payload = {
        "embedding_id": 11,  # Embedding-3
        "name": "退换货政策知识库",
        "description": "退换货政策相关文档",
        "background": "blue",
        "icon": "book"
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/llm-application/open/knowledge",
            headers=headers,
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 200:
            knowledge_id = data.get("data", {}).get("id")
            print(f"知识库创建成功，ID: {knowledge_id}")
            return knowledge_id
        else:
            print(f"创建知识库失败: {data}")
            return None

    except Exception as e:
        print(f"创建知识库时出错: {e}")
        return None

def upload_document(knowledge_id: str) -> Optional[str]:
    """上传文档到知识库"""
    print("正在上传文档...")

    try:
        with open("faq.txt", "rb") as f:
            files = {"files": f}
            data = {
                "knowledge_type": 1,  # 按标题段落切
                "parse_image": "false"
            }

            resp = requests.post(
                f"{BASE_URL}/llm-application/open/document/upload_document/{knowledge_id}",
                headers=headers,
                files=files,
                data=data
            )
            resp.raise_for_status()
            result = resp.json()

        if result.get("code") == 200:
            success_infos = result.get("data", {}).get("successInfos", [])
            if success_infos:
                document_id = success_infos[0].get("documentId")
                print(f"文档上传成功，ID: {document_id}")

                # 等待向量化完成
                if wait_for_embedding_completion(document_id):
                    return document_id

        print(f"文档上传失败: {result}")
        return None

    except Exception as e:
        print(f"上传文档时出错: {e}")
        return None

def retrieve_from_knowledge_base(knowledge_id: str, query: str = "退换货政策的有效期是多久") -> bool:
    """从知识库检索"""
    print(f"\n正在检索: {query}")

    payload = {
        "query": query,
        "knowledge_ids": [knowledge_id],
        "top_k": 5,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/llm-application/open/knowledge/retrieve",
            headers=headers,
            json=payload
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") == 200:
            data = result.get("data", [])
            if data:
                print("\n=== 检索到的原文片段 ===")
                for i, item in enumerate(data, 1):
                    text = item.get("text", "")
                    score = item.get("score", 0)
                    print(f"{i}. [相似度: {score:.3f}] {text}")
                    print("-" * 50)
                return True
            else:
                print("未检索到相关内容")
                return False
        else:
            print(f"检索失败: {result}")
            return False

    except Exception as e:
        print(f"检索时出错: {e}")
        return False

def create_embeddings(texts: List[str]) -> List[List[float]]:
    """创建文本向量"""
    print("正在创建文本向量...")

    all_embeddings = []
    batch_size = 64

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        try:
            resp = requests.post(
                f"{BASE_URL}/paas/v4/embeddings",
                headers=headers,
                json={
                    "model": "embedding-3",
                    "input": batch
                }
            )
            resp.raise_for_status()
            result = resp.json()

            if "data" in result:
                embeddings = [item["embedding"] for item in result["data"]]
                all_embeddings.extend(embeddings)
            else:
                print(f"创建向量失败: {result}")
                return []

        except Exception as e:
            print(f"创建向量时出错: {e}")
            return []

    return all_embeddings

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算余弦相似度"""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot_product / (norm_a * norm_b)

def fallback_search(query: str) -> bool:
    """替代方案：使用embeddings + 关键词匹配"""
    print("\n=== 使用替代方案（embeddings + 关键词匹配）===")

    # 读取faq文件
    try:
        with open("faq.txt", "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return False

    # 分割成段落
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    # 简单的关键词匹配
    query_lower = query.lower()
    matched_paragraphs = []

    for i, para in enumerate(paragraphs):
        # 检查是否包含关键词
        keywords = ["有效期", "退换货", "退货", "换货", "7天", "时间"]
        score = 0
        for keyword in keywords:
            if keyword in para:
                score += 1

        # 标题匹配加分
        if i < len(paragraphs) and "退换货政策" in paragraphs[i]:
            score += 2

        if score > 0:
            matched_paragraphs.append((i, para, score))

    # 按分数排序
    matched_paragraphs.sort(key=lambda x: x[2], reverse=True)

    if matched_paragraphs:
        print("\n=== 匹配的原文片段 ===")
        for i, (idx, para, score) in enumerate(matched_paragraphs[:5], 1):
            print(f"{i}. [匹配度: {score}] {para}")
            print("-" * 50)
        return True
    else:
        print("未找到匹配内容")
        return False

def cleanup_knowledge_base(knowledge_id: str):
    """清理知识库资源"""
    print("\n正在清理知识库...")

    try:
        # 获取文档列表
        resp = requests.get(
            f"{BASE_URL}/llm-application/open/document",
            headers=headers,
            params={"knowledge_id": knowledge_id}
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 200:
            docs = data.get("data", {}).get("list", [])
            for doc in docs:
                doc_id = doc.get("id")
                if doc_id:
                    # 删除文档
                    requests.delete(
                        f"{BASE_URL}/llm-application/open/document/{doc_id}",
                        headers=headers
                    )

        # 删除知识库
        requests.delete(
            f"{BASE_URL}/llm-application/open/knowledge/{knowledge_id}",
            headers=headers
        )

        print(f"知识库 {knowledge_id} 已清理")

    except Exception as e:
        print(f"清理时出错: {e}")

def main():
    print("=== 智谱AI知识库检索测试 ===\n")

    # 方案1：使用托管知识库
    knowledge_id = create_knowledge_base()
    if knowledge_id:
        document_id = upload_document(knowledge_id)
        if document_id:
            # 尝试检索
            if retrieve_from_knowledge_base(knowledge_id):
                print("\n✅ 托管知识库检索成功！")
                cleanup_knowledge_base(knowledge_id)
                return
            else:
                print("\n❌ 托管知识库检索失败，尝试替代方案...")
                cleanup_knowledge_base(knowledge_id)

    # 方案2：替代方案
    print("\n" + "="*50)
    if fallback_search("退换货政策的有效期是多久"):
        print("\n✅ 替代方案检索成功！")
    else:
        print("\n❌ 所有方案都失败了")

if __name__ == "__main__":
    main()