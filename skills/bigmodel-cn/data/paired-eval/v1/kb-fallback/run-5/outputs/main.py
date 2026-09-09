#!/usr/bin/env python3
"""
智谱AI托管知识库检索示例
1. 创建知识库
2. 上传faq.txt文档
3. 等待向量化完成
4. 检索"退换货政策的有效期是多久"
5. 打印检索结果
6. 清理资源
"""

import os
import requests
import time
import json
from typing import List, Dict, Optional

# 配置
API_BASE = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
if not API_KEY:
    raise ValueError("请设置环境变量 ZHIPUAI_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

class ZhipuKnowledgeBase:
    """智谱AI知识库管理类"""

    def __init__(self):
        self.knowledge_id = None
        self.document_id = None

    def create_knowledge_base(self, name: str = "FAQ知识库", description: str = "FAQ文档知识库") -> Dict:
        """创建知识库"""
        url = f"{API_BASE}/llm-application/open/knowledge"
        data = {
            "embedding_id": 11,  # Embedding-3
            "name": name,
            "description": description,
            "background": "blue",
            "icon": "book"
        }

        resp = requests.post(url, headers=HEADERS, json=data)
        result = resp.json()

        if result.get("code") != 200:
            raise Exception(f"创建知识库失败: {result}")

        self.knowledge_id = result["data"]["id"]
        print(f"✓ 创建知识库成功: {self.knowledge_id}")
        return result

    def list_knowledge_bases(self) -> List[Dict]:
        """列出知识库"""
        url = f"{API_BASE}/llm-application/open/knowledge"
        params = {"page": 1, "size": 10}

        resp = requests.get(url, headers=HEADERS, params=params)
        result = resp.json()

        if result.get("code") != 200:
            raise Exception(f"获取知识库列表失败: {result}")

        return result["data"]["list"]

    def upload_document(self, file_path: str) -> Dict:
        """上传文档到知识库"""
        if not self.knowledge_id:
            raise Exception("请先创建知识库")

        url = f"{API_BASE}/llm-application/open/document/upload_document/{self.knowledge_id}"

        with open(file_path, 'rb') as f:
            files = {"files": f}
            data = {
                "knowledge_type": 1,  # 按标题段落切
                "parse_image": "false"
            }

            resp = requests.post(url, headers=HEADERS, files=files, data=data)
            result = resp.json()

        if result.get("code") != 200:
            raise Exception(f"上传文档失败: {result}")

        if not result["data"]["successInfos"]:
            raise Exception("文档上传成功但没有返回document ID")

        self.document_id = result["data"]["successInfos"][0]["documentId"]
        print(f"✓ 上传文档成功: {self.document_id}")
        return result

    def wait_for_embedding_complete(self, max_wait: int = 300, interval: int = 10) -> bool:
        """等待向量化完成"""
        if not self.document_id:
            raise Exception("请先上传文档")

        url = f"{API_BASE}/llm-application/open/document/{self.document_id}"

        start_time = time.time()
        while time.time() - start_time < max_wait:
            resp = requests.get(url, headers=HEADERS)
            result = resp.json()

            if result.get("code") != 200:
                print(f"⚠️ 获取文档状态失败: {result}")
                time.sleep(interval)
                continue

            data = result["data"]
            embedding_stat = data.get("embedding_stat")

            if embedding_stat == 1:
                print("✓ 向量化完成")
                return True
            elif embedding_stat == 2:
                fail_info = data.get("failInfo", {})
                error_msg = fail_info.get("embedding_msg", "未知错误")
                raise Exception(f"向量化失败: {error_msg}")
            else:
                print(f"⏳ 向量化中... (状态: {embedding_stat})")
                time.sleep(interval)

        raise Exception(f"等待向量化超时（{max_wait}秒）")

    def retrieve_knowledge(self, query: str, top_k: int = 5) -> List[Dict]:
        """检索知识库"""
        if not self.knowledge_id:
            raise Exception("请先创建知识库")

        url = f"{API_BASE}/llm-application/open/knowledge/retrieve"
        data = {
            "query": query,
            "knowledge_ids": [self.knowledge_id],
            "top_k": top_k,
            "rerank_status": 1,
            "rerank_model": "rerank-pro"
        }

        resp = requests.post(url, headers=HEADERS, json=data)
        result = resp.json()

        if result.get("code") != 200:
            raise Exception(f"检索失败: {result}")

        return result["data"]

    def delete_document(self) -> bool:
        """删除文档"""
        if not self.document_id:
            return False

        url = f"{API_BASE}/llm-application/open/document/{self.document_id}"
        resp = requests.delete(url, headers=HEADERS)
        result = resp.json()

        if result.get("code") == 200:
            print(f"✓ 删除文档成功: {self.document_id}")
            self.document_id = None
            return True

        print(f"⚠️ 删除文档失败: {result}")
        return False

    def delete_knowledge_base(self) -> bool:
        """删除知识库"""
        if not self.knowledge_id:
            return False

        url = f"{API_BASE}/llm-application/open/knowledge/{self.knowledge_id}"
        resp = requests.delete(url, headers=HEADERS)
        result = resp.json()

        if result.get("code") == 200:
            print(f"✓ 删除知识库成功: {self.knowledge_id}")
            self.knowledge_id = None
            return True

        print(f"⚠️ 删除知识库失败: {result}")
        return False

def alternative_search_approach(faq_content: str, query: str) -> List[str]:
    """替代方案：使用简单的文本匹配"""
    print("\n=== 使用替代方案：文本匹配 ===")

    # 将faq内容按行分割
    lines = faq_content.strip().split('\n')

    # 简单的关键词匹配
    results = []
    query_keywords = ["有效期", "退换货", "期限"]

    for line in lines:
        if any(keyword in line for keyword in query_keywords):
            results.append(line.strip())

    if results:
        print("✓ 找到匹配的内容:")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result}")
        return results
    else:
        print("⚠️ 未找到匹配内容")
        return []

def main():
    """主函数"""
    faq_path = "../run-1/faq.txt"

    # 检查文件是否存在
    if not os.path.exists(faq_path):
        print(f"❌ 找不到FAQ文件: {faq_path}")
        return

    # 读取FAQ内容
    with open(faq_path, 'r', encoding='utf-8') as f:
        faq_content = f.read()

    print("=== 智谱AI知识库检索示例 ===")
    print(f"FAQ文件路径: {faq_path}")
    print(f"FAQ内容长度: {len(faq_content)} 字符")

    kb = ZhipuKnowledgeBase()
    use_knowledge_base = True

    try:
        # 步骤1：创建知识库
        print("\n--- 步骤1：创建知识库 ---")
        kb.create_knowledge_base()

        # 步骤2：上传文档
        print("\n--- 步骤2：上传文档 ---")
        kb.upload_document(faq_path)

        # 步骤3：等待向量化完成
        print("\n--- 步骤3：等待向量化完成 ---")
        kb.wait_for_embedding_complete()

        # 步骤4：检索知识库
        print("\n--- 步骤4：检索知识库 ---")
        query = "退换货政策的有效期是多久"
        print(f"查询问题: {query}")

        retrieval_results = kb.retrieve_knowledge(query)

        if retrieval_results:
            print("✓ 找到检索结果:")
            for i, result in enumerate(retrieval_results, 1):
                print(f"{i}. [相似度: {result.get('score', 0):.3f}] {result['text']}")
                if 'metadata' in result and result['metadata']:
                    print(f"   来源: {result['metadata'].get('doc_name', '未知')}")
        else:
            print("⚠️ 检索结果为空")
            use_knowledge_base = False

    except Exception as e:
        print(f"❌ 知识库操作失败: {e}")
        print("\n可能是以下原因导致:")
        print("1. 账号没有知识库权限")
        print("2. API Key无效或已过期")
        print("3. 服务暂时不可用")
        use_knowledge_base = False

    # 如果知识库不可用，使用替代方案
    if not use_knowledge_base:
        print("\n=== 知识库不可用，使用替代方案 ===")
        alternative_search_approach(faq_content, query)

    # 清理资源
    print("\n--- 清理资源 ---")
    try:
        if kb.document_id:
            kb.delete_document()
        if kb.knowledge_id:
            kb.delete_knowledge_base()
    except Exception as e:
        print(f"⚠️ 清理资源时出错: {e}")

    print("\n=== 完成 ===")

if __name__ == "__main__":
    main()