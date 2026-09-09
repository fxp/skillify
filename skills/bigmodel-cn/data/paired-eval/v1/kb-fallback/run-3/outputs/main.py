#!/usr/bin/env python3
import os
import requests
import time
import json
from typing import Dict, List, Optional

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 全局变量存储创建的资源
created_knowledge_id = None
created_document_id = None


def make_request(method: str, endpoint: str, **kwargs) -> Dict:
    """发送HTTP请求并处理响应"""
    url = f"{BASE_URL}{endpoint}"
    response = requests.request(method, url, headers=HEADERS, **kwargs)
    result = response.json()

    # 检查API响应状态
    if result.get("code") != 200:
        error_msg = result.get("message", "未知错误")
        raise Exception(f"API请求失败: {error_msg}")

    return result


def create_knowledge_base() -> str:
    """创建知识库"""
    global created_knowledge_id

    payload = {
        "embedding_id": 11,  # Embedding-3
        "name": "FAQ知识库",
        "description": "退换货政策等FAQ文档",
        "background": "blue",
        "icon": "book"
    }

    result = make_request("POST", "/llm-application/open/knowledge", json=payload)
    created_knowledge_id = result["data"]["id"]
    print(f"✓ 创建知识库成功，ID: {created_knowledge_id}")

    return created_knowledge_id


def upload_document(knowledge_id: str) -> str:
    """上传文档到知识库"""
    global created_document_id

    with open("faq.txt", "rb") as f:
        files = {"files": f}
        data = {
            "knowledge_type": 1,  # 按标题段落切
            "parse_image": "false"
        }

        result = make_request(
            "POST",
            f"/llm-application/open/document/upload_document/{knowledge_id}",
            files=files,
            data=data
        )

    # 检查上传结果
    if not result["data"]["successInfos"]:
        raise Exception("文档上传失败")

    created_document_id = result["data"]["successInfos"][0]["documentId"]
    print(f"✓ 上传文档成功，ID: {created_document_id}")

    return created_document_id


def wait_for_embedding(document_id: str, max_wait_minutes: int = 10) -> bool:
    """等待文档向量化完成"""
    print("⏳ 等待文档向量化完成...")
    start_time = time.time()

    while time.time() - start_time < max_wait_minutes * 60:
        try:
            result = make_request("GET", f"/llm-application/open/document/{document_id}")
            embedding_stat = result["data"]["embedding_stat"]
            fail_info = result["data"].get("failInfo", {})

            if embedding_stat == 1:
                print("✓ 文档向量化完成")
                return True
            elif embedding_stat == 2:
                error_msg = fail_info.get("embedding_msg", "未知错误")
                raise Exception(f"文档向量化失败: {error_msg}")
            else:
                print(f"  向量化状态: {embedding_stat}，继续等待...")
                time.sleep(10)

        except Exception as e:
            print(f"  检查向量化状态时出错: {str(e)}")
            time.sleep(10)

    raise Exception(f"等待向量化超时（{max_wait_minutes}分钟）")


def retrieve_knowledge(query: str, knowledge_ids: List[str]) -> List[Dict]:
    """检索知识库"""
    payload = {
        "query": query,
        "knowledge_ids": knowledge_ids,
        "top_k": 5,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    result = make_request("POST", "/llm-application/open/knowledge/retrieve", json=payload)
    return result.get("data", [])


def cleanup():
    """清理临时资源"""
    print("\n🧹 清理临时资源...")

    try:
        # 删除文档
        if created_document_id:
            make_request("DELETE", f"/llm-application/open/document/{created_document_id}")
            print(f"✓ 已删除文档: {created_document_id}")

        # 删除知识库
        if created_knowledge_id:
            make_request("DELETE", f"/llm-application/open/knowledge/{created_knowledge_id}")
            print(f"✓ 已删除知识库: {created_knowledge_id}")

    except Exception as e:
        print(f"⚠️ 清理资源时出错: {str(e)}")


def alternative_retrieval():
    """替代检索方案：使用Embeddings + Rerank"""
    print("\n🔄 执行替代检索方案...")

    try:
        # 1. 获取文本向量
        text = "退换货政策的有效期是多久？"
        payload = {
            "model": "embedding-3",
            "input": [text]
        }

        result = make_request("POST", "/paas/v4/embeddings", json=payload)
        query_embedding = result["data"][0]["embedding"]
        print("✓ 获取查询向量成功")

        # 2. 读取FAQ文档并分块
        with open("faq.txt", "r", encoding="utf-8") as f:
            faq_content = f.read()

        # 简单分块：每行作为一个块
        chunks = [line.strip() for line in faq_content.split('\n') if line.strip()]
        print(f"✓ 分块完成，共 {len(chunks)} 个块")

        # 3. 获取所有块的向量
        chunk_texts = chunks[:20]  # 限制数量避免API调用过多
        chunk_embeddings = []

        for chunk in chunk_texts:
            payload = {
                "model": "embedding-3",
                "input": [chunk]
            }
            result = make_request("POST", "/paas/v4/embeddings", json=payload)
            chunk_embeddings.append(result["data"][0]["embedding"])

        print("✓ 获取所有块向量完成")

        # 4. 计算相似度（简单的余弦相似度）
        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x**2 for x in a) ** 0.5
            norm_b = sum(y**2 for y in b) ** 0.5
            return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0

        # 5. 计算相似度并排序
        similarities = []
        for i, chunk_embedding in enumerate(chunk_embeddings):
            similarity = cosine_similarity(query_embedding, chunk_embedding)
            similarities.append((similarity, i, chunk_texts[i]))

        # 6. 排序并返回最相关的结果
        similarities.sort(reverse=True, key=lambda x: x[0])

        print("\n📋 检索结果（原文片段）:")
        for i, (score, idx, text) in enumerate(similarities[:3]):
            print(f"\n--- 结果 {i+1} (相似度: {score:.4f}) ---")
            print(text)

        return similarities[:3]

    except Exception as e:
        print(f"❌ 替代检索方案执行失败: {str(e)}")
        return None


def main():
    """主函数"""
    print("🚀 开始执行知识库检索任务\n")

    # 检查API Key
    if not API_KEY:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        return

    try:
        # 方案1：使用托管知识库
        print("📚 方案1：使用托管知识库")
        print("-" * 50)

        try:
            # 1. 创建知识库
            kb_id = create_knowledge_base()

            # 2. 上传文档
            doc_id = upload_document(kb_id)

            # 3. 等待向量化完成
            wait_for_embedding(doc_id)

            # 4. 检索
            query = "退换货政策的有效期是多久"
            results = retrieve_knowledge(query, [kb_id])

            if results:
                print("\n📋 检索结果（原文片段）:")
                for i, result in enumerate(results, 1):
                    print(f"\n--- 结果 {i} ---")
                    print(result["text"])

                # 成功找到结果，完成任务
                print(f"\n✅ 托管知识库检索成功！共找到 {len(results)} 个相关结果")

        except Exception as e:
            print(f"❌ 托管知识库方案失败: {str(e)}")
            print("\n🔄 尝试替代方案...")

            # 方案2：替代检索方案
            alternative_results = alternative_retrieval()
            if alternative_results:
                print(f"\n✅ 替代检索方案成功！共找到 {len(alternative_results)} 个相关结果")
            else:
                print("\n❌ 所有检索方案都失败了")

    except Exception as e:
        print(f"\n❌ 程序执行出错: {str(e)}")

    finally:
        # 清理资源
        cleanup()


if __name__ == "__main__":
    main()