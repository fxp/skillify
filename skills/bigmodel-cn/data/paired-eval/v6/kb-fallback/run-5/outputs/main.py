#!/usr/bin/env python3
import os
import requests
import json
import time
import io
from pathlib import Path

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = "https://open.bigmodel.cn/api"

faq_file = Path("../run-3/faq.txt")
question = "退换货政策的有效期是多久"

def print_header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_error(title, error):
    print(f"\n{'!'*60}")
    print(f" {title}")
    print(f" 错误: {error}")
    print(f"{'!'*60}")

def create_knowledge_base():
    """创建知识库"""
    print_header("1. 创建知识库")

    url = f"{BASE_URL}/llm-application/open/knowledge"
    payload = {
        "embedding_id": 11,  # Embedding-3
        "name": "退换货政策知识库",
        "description": "退换货政策相关文档",
        "background": "blue",
        "icon": "book"
    }

    response = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}"}, json=payload)
    result = response.json()

    if result.get("code") != 200:
        print_error("知识库创建失败", result.get("message", "未知错误"))
        return None

    knowledge_id = result["data"]["id"]
    print(f"✓ 知识库创建成功: {knowledge_id}")
    return knowledge_id

def upload_document(knowledge_id, file_path):
    """上传文档到知识库"""
    print_header(f"2. 上传文档 {file_path}")

    url = f"{BASE_URL}/llm-application/open/document/upload_document/{knowledge_id}"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 将文本内容作为临时文件上传
    files = {
        'files': ('faq.txt', io.BytesIO(content.encode('utf-8')), 'text/plain')
    }
    data = {
        'knowledge_type': '1',  # 按标题段落切分
        'parse_image': 'false'
    }

    response = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}"}, files=files, data=data)
    result = response.json()

    if result.get("code") != 200:
        print_error("文档上传失败", result.get("message", "未知错误"))
        return None

    if result.get("data", {}).get("successInfos"):
        document_id = result["data"]["successInfos"][0]["documentId"]
        print(f"✓ 文档上传成功: {document_id}")
        return document_id
    else:
        print_error("文档上传失败", result.get("data", {}).get("failedInfos", [{}])[0].get("message", "未知错误"))
        return None

def wait_for_embedding_completion(knowledge_id, document_id, max_attempts=30):
    """等待文档向量化完成"""
    print_header(f"3. 等待文档向量化完成")

    url = f"{BASE_URL}/llm-application/open/document/{document_id}"

    for attempt in range(max_attempts):
        response = requests.get(url, headers={"Authorization": f"Bearer {API_KEY}"})
        result = response.json()

        if result.get("code") != 200:
            print_error("获取文档状态失败", result.get("message", "未知错误"))
            return False

        embedding_stat = result.get("data", {}).get("embedding_stat", 0)

        if embedding_stat == 1:  # 成功
            print(f"✓ 文档向量化完成 (尝试 {attempt + 1}/{max_attempts})")
            return True
        elif embedding_stat == 2:  # 失败
            fail_msg = result.get("data", {}).get("failInfo", {}).get("embedding_msg", "未知错误")
            print_error("文档向量化失败", fail_msg)
            return False
        else:  # 处理中 (0)
            print(f"⏳ 文档处理中... (尝试 {attempt + 1}/{max_attempts}), embedding_stat: {embedding_stat}")
            time.sleep(2)  # 等待2秒后重试

    print_error("等待超时", f"在 {max_attempts} 次尝试后文档仍未完成向量化")
    return False

def retrieve_from_knowledge_base(knowledge_id):
    """从知识库检索"""
    print_header("4. 从托管知识库检索")

    url = f"{BASE_URL}/llm-application/open/knowledge/retrieve"
    payload = {
        "query": question,
        "knowledge_ids": [knowledge_id],
        "top_k": 5,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    response = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}"}, json=payload)
    result = response.json()

    if result.get("code") != 200:
        print_error("知识库检索失败", result.get("message", "未知错误"))
        return None

    data = result.get("data", [])
    if data:
        print(f"✓ 找到 {len(data)} 条相关结果:")
        for i, item in enumerate(data, 1):
            print(f"\n{i}. 相关度: {item.get('score', 0):.3f}")
            print(f"   原文: {item.get('text', 'N/A')}")
            print(f"   来源: {item.get('metadata', {}).get('doc_name', 'N/A')}")
        return data
    else:
        print("⚠️ 知识库未找到相关内容")
        return []

def cleanup_knowledge_base(knowledge_id):
    """清理知识库"""
    print_header("5. 清理临时资源")

    # 获取知识库中的文档列表
    doc_url = f"{BASE_URL}/llm-application/open/document"
    doc_response = requests.get(doc_url, headers={"Authorization": f"Bearer {API_KEY}"},
                              params={"knowledge_id": knowledge_id})

    if doc_response.json().get("code") == 200:
        doc_list = doc_response.json().get("data", {}).get("list", [])
        for doc in doc_list:
            doc_id = doc.get("id")
            print(f"删除文档: {doc.get('name', 'N/A')} (ID: {doc_id})")
            delete_url = f"{BASE_URL}/llm-application/open/document/{doc_id}"
            requests.delete(delete_url, headers={"Authorization": f"Bearer {API_KEY}"})

    # 删除知识库
    print(f"删除知识库: {knowledge_id}")
    kb_url = f"{BASE_URL}/llm-application/open/knowledge/{knowledge_id}"
    requests.delete(kb_url, headers={"Authorization": f"Bearer {API_KEY}"})

    print("✓ 临时资源清理完成")

def build_custom_rag():
    """自建 RAG 检索方案（当托管知识库不可用时使用）"""
    print_header("使用自建 RAG 检索方案")

    # 1. 读取 FAQ 文档并分块
    with open(faq_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 简单按段落分块
    chunks = []
    lines = content.split('\n')
    current_chunk = ""

    for line in lines:
        if line.strip() and not line.startswith(('1.', '2.', '3.', '4.', '5.')):
            # 这是正文内容
            if current_chunk and len(current_chunk) + len(line) + 1 < 500:  # 合并小段落
                current_chunk += "\n" + line if current_chunk else line
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line
        else:
            # 这是标题或编号，作为分块边界
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = line if line.strip() else ""

    if current_chunk:
        chunks.append(current_chunk.strip())

    print(f"✓ 文档分块完成，共 {len(chunks)} 个块")

    # 2. 生成查询和文档的 embeddings
    def get_embeddings(texts, model="embedding-3"):
        url = f"{BASE_URL}/paas/v4/embeddings"
        payload = {
            "model": model,
            "input": texts
        }

        response = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}"}, json=payload)
        if response.status_code != 200:
            print_error("Embeddings 调用失败", response.text)
            return None

        result = response.json()
        if result.get("code") != 200:
            print_error("Embeddings 调用失败", result.get("message", "未知错误"))
            return None

        embeddings = []
        for item in result.get("data", []):
            embeddings.append(item["embedding"])

        return embeddings

    print("\n生成查询向量...")
    query_embedding = get_embeddings([question])
    if not query_embedding:
        return None

    print("\n生成文档向量...")
    doc_embeddings = get_embeddings(chunks)
    if not doc_embeddings:
        return None

    # 3. 计算相似度并排序
    def cosine_similarity(a, b):
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0

    # 计算查询与每个文档块的相似度
    similarities = []
    for i, emb in enumerate(doc_embeddings):
        similarity = cosine_similarity(query_embedding[0], emb)
        similarities.append((i, similarity))

    # 按相似度排序
    similarities.sort(key=lambda x: x[1], reverse=True)

    # 4. 使用 rerank 进行精排
    print("\n使用 rerank 进行精排...")

    # 取前10个候选
    top_k_candidates = min(10, len(chunks))
    candidate_indices = [idx for idx, _ in similarities[:top_k_candidates]]
    candidate_texts = [chunks[idx] for idx in candidate_indices]

    rerank_payload = {
        "model": "rerank",
        "query": question,
        "documents": candidate_texts,
        "top_n": 5,
        "return_documents": True
    }

    response = requests.post(
        f"{BASE_URL}/paas/v4/rerank",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=rerank_payload
    )

    if response.status_code != 200:
        print_error("Rerank 调用失败", response.text)
        # 使用原始相似度结果作为备选
        results = []
        for i in range(min(5, len(similarities))):
            idx, score = similarities[i]
            results.append({
                "index": idx,
                "text": chunks[idx],
                "score": score
            })
    else:
        result = response.json()
        if result.get("code") != 200:
            print_error("Rerank 调用失败", result.get("message", "未知错误"))
            # 使用原始相似度结果作为备选
            results = []
            for i in range(min(5, len(similarities))):
                idx, score = similarities[i]
                results.append({
                    "index": idx,
                    "text": chunks[idx],
                    "score": score
                })
        else:
            results = []
            for item in result.get("results", []):
                original_idx = candidate_indices[item["index"]]
                results.append({
                    "index": original_idx,
                    "text": item["document"],
                    "score": item["relevance_score"]
                })

    # 5. 打印结果
    print(f"\n✓ 自建 RAG 找到 {len(results)} 条相关结果:")
    for i, item in enumerate(results, 1):
        print(f"\n{i}. 相关度: {item.get('score', 0):.3f}")
        print(f"   原文: {item.get('text', 'N/A')}")

    return results

def main():
    if not API_KEY:
        print_error("环境变量未设置", "请设置 ZHIPUAI_API_KEY 环境变量")
        return

    if not faq_file.exists():
        print_error("文件未找到", f"FAQ 文件不存在: {faq_file}")
        return

    try:
        # 尝试使用托管知识库
        print("尝试使用托管知识库...")

        # 创建知识库
        knowledge_id = create_knowledge_base()
        if not knowledge_id:
            raise Exception("创建知识库失败")

        # 上传文档
        document_id = upload_document(knowledge_id, str(faq_file))
        if not document_id:
            raise Exception("文档上传失败")

        # 等待向量化完成
        if not wait_for_embedding_completion(knowledge_id, document_id):
            raise Exception("文档向量化失败或超时")

        # 检索
        retrieval_results = retrieve_from_knowledge_base(knowledge_id)

        # 无论成功与否，都清理资源
        cleanup_knowledge_base(knowledge_id)

        if retrieval_results:
            print("\n🎉 托管知识库检索成功！")
            return

        print("\n⚠️ 托管知识库检索未找到内容，尝试自建 RAG...")

    except Exception as e:
        print(f"\n托管知识库方案失败: {str(e)}")
        print("转向自建 RAG 方案...")

    # 如果托管知识库不可用，使用自建 RAG
    build_custom_rag()

if __name__ == "__main__":
    main()