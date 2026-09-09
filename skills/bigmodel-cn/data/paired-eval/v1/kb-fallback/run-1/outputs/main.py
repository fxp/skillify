#!/usr/bin/env python3
"""
智谱AI知识库检索示例
使用托管知识库或备用的 embeddings 方式检索FAQ内容
"""

import os
import requests
import time
import json
from typing import Dict, List, Optional, Tuple

# API配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 检查API Key
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def make_request(method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None) -> Dict:
    """发起HTTP请求并处理响应"""
    url = f"{BASE_URL}{endpoint}"

    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=data)
        elif method.upper() == "POST":
            if files:
                resp = requests.post(url, headers=headers, files=files, data=data)
            else:
                resp = requests.post(url, headers=headers, json=data)
        elif method.upper() == "PUT":
            resp = requests.put(url, headers=headers, json=data)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"不支持的HTTP方法: {method}")

        resp.raise_for_status()
        result = resp.json()

        # 检查业务错误码
        if "code" in result and result["code"] != 200:
            raise Exception(f"API错误: {result.get('message', '未知错误')} (code: {result['code']})")

        return result

    except requests.exceptions.RequestException as e:
        raise Exception(f"HTTP请求失败: {str(e)}")


def create_knowledge_base() -> str:
    """创建知识库"""
    print("正在创建知识库...")
    data = {
        "embedding_id": 11,  # Embedding-3
        "name": "FAQ知识库",
        "description": "常见问题解答知识库",
        "background": "blue",
        "icon": "book"
    }

    result = make_request("POST", "/llm-application/open/knowledge", data)
    knowledge_id = result["data"]["id"]
    print(f"知识库创建成功，ID: {knowledge_id}")
    return knowledge_id


def upload_document(knowledge_id: str, file_path: str) -> str:
    """上传文档到知识库"""
    print(f"正在上传文件: {file_path}")

    with open(file_path, 'rb') as f:
        data = {
            "knowledge_type": "1",  # 按标题段落切分
            "parse_image": "false"
        }
        result = make_request("POST", f"/llm-application/open/document/upload_document/{knowledge_id}",
                            data=data, files={"files": f})

    # 获取文档ID
    if result["data"]["successInfos"]:
        doc_id = result["data"]["successInfos"][0]["documentId"]
        print(f"文件上传成功，文档ID: {doc_id}")
        return doc_id
    else:
        raise Exception("文件上传失败")


def wait_for_embedding_completion(knowledge_id: str, doc_id: str, timeout: int = 300) -> bool:
    """等待文档向量化完成"""
    print("等待文档向量化完成...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            result = make_request("GET", f"/llm-application/open/document/{doc_id}")
            embedding_stat = result["data"]["embedding_stat"]
            fail_info = result["data"].get("failInfo", {})

            if embedding_stat == 1:
                print("向量化完成！")
                return True
            elif embedding_stat == 2:
                error_msg = fail_info.get("embedding_msg", "未知错误")
                raise Exception(f"向量化失败: {error_msg}")
            else:
                print(f"向量化进行中... 状态: {embedding_stat}")
                time.sleep(5)

        except Exception as e:
            print(f"检查状态时出错: {e}")
            time.sleep(5)

    raise Exception("等待向量化超时")


def search_in_knowledge_base(knowledge_id: str, query: str) -> List[Dict]:
    """在知识库中搜索"""
    print(f"正在搜索: {query}")

    data = {
        "query": query,
        "knowledge_ids": [knowledge_id],
        "top_k": 5,
        "rerank_status": 1,
        "rerank_model": "rerank-pro"
    }

    result = make_request("POST", "/llm-application/open/knowledge/retrieve", data)
    return result["data"]


def delete_knowledge_base(knowledge_id: str):
    """删除知识库"""
    print("正在清理知识库...")
    try:
        make_request("DELETE", f"/llm-application/open/knowledge/{knowledge_id}")
        print("知识库已删除")
    except Exception as e:
        print(f"删除知识库时出错: {e}")


def alternative_embeddings_approach() -> bool:
    """备用方案：使用 embeddings 进行相似度搜索"""
    print("\n尝试备用方案：使用 embeddings 进行语义搜索")

    try:
        # 读取FAQ文件
        with open("faq.txt", "r", encoding="utf-8") as f:
            faq_content = f.read()

        # 将FAQ按段落分割
        paragraphs = [p.strip() for p in faq_content.split("\n\n") if p.strip()]

        print(f"加载了 {len(paragraphs)} 个FAQ段落")

        # 创建查询的embedding
        query = "退换货政策的有效期是多久"
        print(f"正在为查询创建embedding: {query}")

        embed_result = make_request("POST", "/paas/v4/embeddings",
                                 {"model": "embedding-3", "input": [query]})
        query_embedding = embed_result["data"][0]["embedding"]

        # 为每个段落创建embedding
        print("正在为FAQ段落创建embeddings...")
        embeddings = []

        for i, para in enumerate(paragraphs):
            if i % 5 == 0:
                print(f"处理段落 {i+1}/{len(paragraphs)}")

            para_result = make_request("POST", "/paas/v4/embeddings",
                                     {"model": "embedding-3", "input": [para]})
            embeddings.append({
                "text": para,
                "embedding": para_result["data"][0]["embedding"]
            })

        # 计算相似度
        def cosine_similarity(a: List[float], b: List[float]) -> float:
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x ** 2 for x in a) ** 0.5
            norm_b = sum(y ** 2 for y in b) ** 0.5
            return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0

        # 找到最相似的段落
        similarities = []
        for emb in embeddings:
            sim = cosine_similarity(query_embedding, emb["embedding"])
            similarities.append((emb["text"], sim))

        # 按相似度排序
        similarities.sort(key=lambda x: x[1], reverse=True)

        # 打印最相关的结果
        print("\n=== 最相关的FAQ段落 ===")
        for i, (text, score) in enumerate(similarities[:3]):
            print(f"\n相似度 {score:.4f}:")
            print(text[:200] + "..." if len(text) > 200 else text)

        return True

    except Exception as e:
        print(f"备用方案执行失败: {e}")
        return False


def main():
    """主函数"""
    print("=== 智谱AI知识库检索示例 ===\n")

    # 方案1：使用托管知识库
    try:
        # 创建知识库
        knowledge_id = create_knowledge_base()

        # 上传文档
        doc_id = upload_document(knowledge_id, "faq.txt")

        # 等待向量化完成
        wait_for_embedding_completion(knowledge_id, doc_id)

        # 执行检索
        query = "退换货政策的有效期是多久"
        search_results = search_in_knowledge_base(knowledge_id, query)

        if search_results:
            print("\n=== 托管知识库检索结果 ===")
            for i, result in enumerate(search_results, 1):
                print(f"\n结果 {i} (相似度: {result['score']:.4f}):")
                print(result['text'])
        else:
            print("\n未找到相关内容")

        # 清理
        delete_knowledge_base(knowledge_id)
        return True

    except Exception as e:
        print(f"\n托管知识库方案失败: {e}")
        print("正在尝试备用方案...\n")

        # 方案2：使用 embeddings
        return alternative_embeddings_approach()


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n=== 任务完成 ===")
        else:
            print("\n=== 所有方案均失败 ===")
    except Exception as e:
        print(f"\n程序执行出错: {e}")