#!/usr/bin/env python3
import os
import requests
import json
import time
import shutil
from pathlib import Path

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# FAQ 文件路径
FAQ_FILE = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/v1/kb-fallback/run-3/faq.txt"
TEMP_DIR = "/tmp/zhipu_kb_test"

def cleanup_temp_resources():
    """清理临时资源"""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        print("已清理临时资源")

def test_knowledge_base_approach():
    """测试托管知识库方案"""
    print("=== 尝试托管知识库方案 ===")

    # 创建临时目录
    os.makedirs(TEMP_DIR, exist_ok=True)

    try:
        # 1. 创建知识库
        print("\n1. 创建知识库...")
        kb_resp = requests.post(
            f"{BASE_URL}/llm-application/open/knowledge",
            headers=headers,
            json={
                "embedding_id": 11,  # Embedding-3
                "name": "FAQ测试知识库",
                "description": "包含退换货政策的FAQ",
                "background": "blue",
                "icon": "book"
            }
        )

        if kb_resp.json().get("code") != 200:
            print(f"创建知识库失败: {kb_resp.json()}")
            return False, None

        kb_id = kb_resp.json()["data"]["id"]
        print(f"✓ 知识库创建成功: {kb_id}")

        # 2. 上传FAQ文档
        print("\n2. 上传FAQ文档...")
        shutil.copy(FAQ_FILE, os.path.join(TEMP_DIR, "faq.txt"))

        with open(os.path.join(TEMP_DIR, "faq.txt"), "rb") as f:
            upload_resp = requests.post(
                f"{BASE_URL}/llm-application/open/document/upload_document/{kb_id}",
                headers=headers,
                files={"files": f},
                data={"knowledge_type": 1}  # 按标题段落切分
            )

        if upload_resp.json().get("code") != 200:
            print(f"上传文档失败: {upload_resp.json()}")
            return False, None

        doc_id = upload_resp.json()["data"]["successInfos"][0]["documentId"]
        print(f"✓ 文档上传成功: {doc_id}")

        # 3. 等待向量化完成
        print("\n3. 等待向量化完成...")
        max_wait = 60  # 最多等待60秒
        wait_time = 0
        embedding_stat = None

        while wait_time < max_wait:
            doc_resp = requests.get(
                f"{BASE_URL}/llm-application/open/document/{doc_id}",
                headers=headers
            )

            if doc_resp.json().get("code") == 200:
                embedding_stat = doc_resp.json()["data"]["embedding_stat"]
                if embedding_stat == 1:
                    print("✓ 向量化完成")
                    break
                elif embedding_stat == 2:
                    print(f"✗ 向量化失败: {doc_resp.json()['data'].get('failInfo', {})}")
                    return False, None
                else:
                    print(f"向量化中... (状态: {embedding_stat})")
                    time.sleep(5)
                    wait_time += 5
            else:
                print(f"获取文档状态失败: {doc_resp.json()}")
                time.sleep(5)
                wait_time += 5

        if embedding_stat != 1:
            print("✗ 向量化超时")
            return False, None

        # 4. 检索
        print("\n4. 执行检索...")
        query = "退换货政策的有效期是多久"
        retrieve_resp = requests.post(
            f"{BASE_URL}/llm-application/open/knowledge/retrieve",
            headers=headers,
            json={
                "query": query,
                "knowledge_ids": [kb_id],
                "top_k": 5,
                "rerank_status": 1,
                "rerank_model": "rerank-pro"
            }
        )

        if retrieve_resp.json().get("code") != 200:
            print(f"检索失败: {retrieve_resp.json()}")
            return False, None

        results = retrieve_resp.json()["data"]
        print(f"✓ 检索成功，找到 {len(results)} 条结果")

        # 5. 打印检索结果
        print("\n=== 检索结果 ===")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. [相似度: {result['score']:.3f}]")
            print(f"原文片段: {result['text']}")
            if "doc_name" in result.get("metadata", {}):
                print(f"来源文档: {result['metadata']['doc_name']}")
            print("-" * 50)

        return True, kb_id

    except Exception as e:
        print(f"托管知识库方案出错: {str(e)}")
        return False, None

def test_embedding_rerank_approach():
    """测试自建 embedding + rerank 替代方案"""
    print("\n=== 尝试自建 embedding + rerank 方案 ===")

    try:
        # 1. 读取 FAQ 文档
        with open(FAQ_FILE, "r", encoding="utf-8") as f:
            faq_content = f.read()

        # 2. 简单的文本预处理和分块
        lines = faq_content.strip().split('\n')
        chunks = []
        current_chunk = ""

        for line in lines:
            if line.strip():  # 非空行
                # 检查是否是问题（以问号结尾）
                if line.strip().endswith('?'):
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line.strip() + "\n"
                else:
                    current_chunk += line.strip() + "\n"

        if current_chunk:
            chunks.append(current_chunk.strip())

        print(f"✓ 文档分块完成，共 {len(chunks)} 个块")

        # 3. 使用 Embedding API 获取每个块的向量
        print("\n3. 计算文本向量...")
        chunk_embeddings = []

        for i, chunk in enumerate(chunks[:20]):  # 限制处理前20个块以避免API限制
            print(f"  处理第 {i+1}/{len(chunks)} 个块...")
            embed_resp = requests.post(
                f"{BASE_URL}/paas/v4/embeddings",
                headers=headers,
                json={
                    "model": "embedding-2",
                    "input": chunk
                }
            )

            if embed_resp.json().get("code") == 200:
                embedding = embed_resp.json()["data"][0]["embedding"]
                chunk_embeddings.append({
                    "text": chunk,
                    "embedding": embedding
                })
            else:
                print(f"  嵌入计算失败: {embed_resp.json()}")

        print(f"✓ 成功计算 {len(chunk_embeddings)} 个文本块的向量")

        # 4. 查询向量
        query = "退换货政策的有效期是多久"
        query_resp = requests.post(
            f"{BASE_URL}/paas/v4/embeddings",
            headers=headers,
            json={
                "model": "embedding-2",
                "input": query
            }
        )

        if query_resp.json().get("code") != 200:
            print(f"查询向量计算失败: {query_resp.json()}")
            return False

        query_embedding = query_resp.json()["data"][0]["embedding"]

        # 5. 计算相似度并排序
        print("\n5. 计算相似度...")
        similarities = []

        for chunk in chunk_embeddings:
            # 简单的余弦相似度计算
            sim = sum(a * b for a, b in zip(query_embedding, chunk["embedding"])) / (
                sum(a * a for a in query_embedding) ** 0.5 *
                sum(b * b for b in chunk["embedding"]) ** 0.5
            )
            similarities.append((sim, chunk["text"]))

        # 排序并获取Top 5
        similarities.sort(reverse=True, key=lambda x: x[0])
        top_5 = similarities[:5]

        # 6. 使用Rerank API重排
        print("\n6. 使用Rerank API重排...")
        rerank_texts = [text for _, text in top_5]
        rerank_resp = requests.post(
            f"{BASE_URL}/paas/v4/rerank",
            headers=headers,
            json={
                "model": "rerank-pro",
                "query": query,
                "documents": rerank_texts
            }
        )

        if rerank_resp.json().get("code") == 200:
            rerank_results = rerank_resp.json()["data"]
            print("✓ Rerank完成")
        else:
            print(f"Rerank失败，使用原始结果: {rerank_resp.json()}")
            rerank_results = [{"relevance_score": score, "text": text} for score, text in top_5]

        # 7. 打印结果
        print("\n=== 检索结果 ===")
        for i, result in enumerate(rerank_results[:5], 1):
            print(f"\n{i}. [相关度: {result.get('relevance_score', top_5[i-1][0]):.3f}]")
            print(f"原文片段: {result['text']}")
            print("-" * 50)

        return True

    except Exception as e:
        print(f"自建embedding方案出错: {str(e)}")
        return False

def main():
    print("开始执行FAQ检索任务...")

    # 方案1：尝试托管知识库
    kb_success, kb_id = test_knowledge_base_approach()

    if kb_success:
        print("\n✓ 托管知识库方案成功完成！")
        # 清理知识库
        if kb_id:
            print("\n5. 清理知识库...")
            delete_resp = requests.delete(
                f"{BASE_URL}/llm-application/open/knowledge/{kb_id}",
                headers=headers
            )
            if delete_resp.json().get("code") == 200:
                print("✓ 知识库已删除")
            else:
                print(f"⚠ 知识库删除失败: {delete_resp.json()}")
    else:
        print("\n✗ 托管知识库方案失败，尝试替代方案...")
        # 方案2：自建embedding + rerank
        embedding_success = test_embedding_rerank_approach()

        if embedding_success:
            print("\n✓ 自建embedding方案成功完成！")
        else:
            print("\n✗ 所有方案都失败了")

    # 清理临时资源
    cleanup_temp_resources()

if __name__ == "__main__":
    main()