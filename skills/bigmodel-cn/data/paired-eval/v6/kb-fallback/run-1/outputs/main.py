#!/usr/bin/env python3
"""
智谱AI知识库检索示例
1. 首先尝试使用托管知识库
2. 如果不可用，则使用本地embedding+相似度检索作为替代方案
"""

import os
import requests
import json
import time
import tempfile
import shutil
from typing import List, Dict, Optional

# API配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 读取FAQ文件
def read_faq_file(faq_path: str) -> str:
    """读取FAQ文件内容"""
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取FAQ文件失败: {e}")
        return None

# 托管知识库相关函数
class ManagedKnowledgeBase:
    """托管知识库操作类"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.knowledge_id = None
        self.document_id = None

    def create_knowledge_base(self, name: str = "FAQ知识库") -> bool:
        """创建知识库"""
        try:
            url = f"{BASE_URL}/llm-application/open/knowledge"
            data = {
                "embedding_id": 11,  # Embedding-3
                "name": name,
                "description": "FAQ退换货政策知识库",
                "background": "blue",
                "icon": "book"
            }

            resp = requests.post(url, headers=self.headers, json=data)
            result = resp.json()

            if result.get("code") == 200:
                self.knowledge_id = result["data"]["id"]
                print(f"✅ 成功创建知识库，ID: {self.knowledge_id}")
                return True
            else:
                print(f"❌ 创建知识库失败: {result}")
                return False

        except Exception as e:
            print(f"❌ 创建知识库异常: {e}")
            return False

    def upload_document(self, faq_content: str) -> bool:
        """上传文档到知识库"""
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
                tmp.write(faq_content)
                tmp_path = tmp.name

            # 上传文件
            url = f"{BASE_URL}/llm-application/open/document/upload_document/{self.knowledge_id}"

            with open(tmp_path, 'rb') as f:
                files = {"files": f}
                data = {
                    "knowledge_type": 1,  # 按标题段落切分
                    "parse_image": "false"
                }

                resp = requests.post(url, headers=self.headers, files=files, data=data)

            # 删除临时文件
            os.unlink(tmp_path)

            result = resp.json()

            if result.get("code") == 200:
                success_infos = result["data"]["successInfos"]
                if success_infos:
                    self.document_id = success_infos[0]["documentId"]
                    print(f"✅ 成功上传文档，ID: {self.document_id}")

                    # 等待向量化完成（最多等待2分钟）
                    return self._wait_for_embedding()
                else:
                    print("❌ 上传文档失败：无成功信息")
                    return False
            else:
                print(f"❌ 上传文档失败: {result}")
                return False

        except Exception as e:
            print(f"❌ 上传文档异常: {e}")
            return False

    def _wait_for_embedding(self, max_wait: int = 120) -> bool:
        """等待文档向量化完成"""
        print("⏳ 等待文档向量化...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                url = f"{BASE_URL}/llm-application/open/document/{self.document_id}"
                resp = requests.get(url, headers=self.headers)
                result = resp.json()

                if result.get("code") == 200:
                    embedding_stat = result["data"]["embedding_stat"]
                    if embedding_stat == 1:  # 向量化成功
                        print("✅ 文档向量化完成")
                        return True
                    elif embedding_stat == 2:  # 向量化失败
                        fail_info = result["data"]["failInfo"]
                        print(f"❌ 文档向量化失败: {fail_info}")
                        return False

                time.sleep(5)

            except Exception as e:
                print(f"⚠️ 检查向量化状态异常: {e}")
                time.sleep(5)

        print("❌ 等待向量化超时")
        return False

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """检索知识库"""
        try:
            url = f"{BASE_URL}/llm-application/open/knowledge/retrieve"
            data = {
                "query": query,
                "knowledge_ids": [self.knowledge_id],
                "top_k": top_k,
                "rerank_status": 1,
                "rerank_model": "rerank-pro"
            }

            resp = requests.post(url, headers=self.headers, json=data)
            result = resp.json()

            if result.get("code") == 200:
                return result["data"]
            else:
                print(f"❌ 检索失败: {result}")
                return []

        except Exception as e:
            print(f"❌ 检索异常: {e}")
            return []

    def clean_up(self):
        """清理资源"""
        if self.document_id:
            try:
                url = f"{BASE_URL}/llm-application/open/document/{self.document_id}"
                requests.delete(url, headers=self.headers)
                print(f"🗑️ 已删除文档: {self.document_id}")
            except:
                pass

        if self.knowledge_id:
            try:
                url = f"{BASE_URL}/llm-application/open/knowledge/{self.knowledge_id}"
                requests.delete(url, headers=self.headers)
                print(f"🗑️ 已删除知识库: {self.knowledge_id}")
            except:
                pass

# 本地embedding检索替代方案
class LocalEmbeddingRetrieval:
    """本地embedding检索替代方案"""

    def __init__(self):
        # 这里简化处理，使用关键词匹配
        # 实际项目中可以使用 sentence-transformers 等库
        self.faq_chunks = []

    def process_faq(self, faq_content: str):
        """处理FAQ内容，切分成块"""
        lines = faq_content.split('\n')
        current_section = ""
        chunks = []

        for line in lines:
            line = line.strip()
            if line and line[0].isdigit() and '.' in line:
                # 新的章节
                if current_section:
                    chunks.append(current_section.strip())
                current_section = line + '\n'
            elif line and (line.startswith('-') or line.startswith('•')):
                # 条目
                current_section += line + '\n'
            elif line:
                # 普通行
                current_section += line + '\n'

        if current_section:
            chunks.append(current_section.strip())

        self.faq_chunks = chunks

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        """基于关键词匹配的检索"""
        # 简单的关键词匹配
        query_words = set(query.lower().split())
        results = []

        for i, chunk in enumerate(self.faq_chunks):
            chunk_words = set(chunk.lower().split())
            # 计算Jaccard相似度
            intersection = len(query_words & chunk_words)
            union = len(query_words | chunk_words)
            similarity = intersection / union if union > 0 else 0

            if similarity > 0:
                results.append({
                    "text": chunk,
                    "score": similarity,
                    "metadata": {
                        "index": i,
                        "chunk_id": f"chunk-{i:03d}"
                    }
                })

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

def main():
    """主函数"""
    if not API_KEY:
        print("❌ 错误：请设置环境变量 ZHIPUAI_API_KEY")
        return

    faq_path = "../v1/kb-fallback/run-1/faq.txt"
    faq_content = read_faq_file(faq_path)

    if not faq_content:
        print("❌ 无法读取FAQ文件")
        return

    print("=" * 50)
    print("智谱AI知识库检索示例")
    print("=" * 50)

    # 方案一：尝试托管知识库
    print("\n🔄 方案一：尝试使用托管知识库...")
    kb = ManagedKnowledgeBase(API_KEY)

    try:
        # 1. 创建知识库
        if not kb.create_knowledge_base():
            raise Exception("创建知识库失败")

        # 2. 上传文档
        if not kb.upload_document(faq_content):
            raise Exception("上传文档失败")

        # 3. 执行检索
        query = "退换货政策的有效期是多久"
        print(f"\n🔍 正在检索: {query}")
        results = kb.retrieve(query)

        if results:
            print("\n✅ 托管知识库检索结果:")
            print("-" * 30)
            for i, result in enumerate(results, 1):
                print(f"{i}. 【相似度: {result['score']:.3f}】")
                print(f"   {result['text']}")
                print()

            print("📌 成功使用托管知识库检索到内容！")
            return

    except Exception as e:
        print(f"⚠️ 托管知识库方案失败: {e}")
    finally:
        # 清理资源
        kb.clean_up()

    # 方案二：本地embedding检索（替代方案）
    print("\n🔄 方案二：使用本地embedding检索（替代方案）...")
    try:
        local_retriever = LocalEmbeddingRetrieval()
        local_retriever.process_faq(faq_content)

        query = "退换货政策的有效期是多久"
        print(f"\n🔍 正在检索: {query}")
        results = local_retriever.retrieve(query)

        if results:
            print("\n✅ 本地检索结果:")
            print("-" * 30)
            for i, result in enumerate(results, 1):
                print(f"{i}. 【相似度: {result['score']:.3f}】")
                print(f"   {result['text']}")
                print()

            print("📌 使用本地检索方案成功检索到内容！")
        else:
            print("❌ 本地检索未找到相关内容")

    except Exception as e:
        print(f"❌ 本地检索失败: {e}")

if __name__ == "__main__":
    main()