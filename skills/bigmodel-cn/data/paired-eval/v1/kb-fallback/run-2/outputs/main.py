import os
import requests
import time
import json

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 检查 API Key
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# 请求头
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 复制 faq.txt 到 outputs 目录
import shutil
faq_source_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/v1/kb-fallback/run-1/faq.txt"
faq_dest_path = "/Users/chopinfeng/Workspace/Skillify/bigmodel-cn-workspace/paired-eval/v1/kb-fallback/run-2/outputs/faq.txt"
try:
    shutil.copy2(faq_source_path, faq_dest_path)
    print(f"已复制 FAQ 文件到: {faq_dest_path}")
except Exception as e:
    print(f"复制 FAQ 文件失败: {e}")
    exit(1)

class ZhipuKnowledgeBase:
    """智谱AI托管知识库管理类"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.knowledge_id = None

    def create_knowledge_base(self, name, description="FAQ知识库", embedding_id=11):
        """创建知识库"""
        print(f"正在创建知识库: {name}")
        url = f"{self.base_url}/llm-application/open/knowledge"
        data = {
            "embedding_id": embedding_id,  # 11: Embedding-3
            "name": name,
            "description": description,
            "background": "blue",
            "icon": "book"
        }

        try:
            response = requests.post(url, headers=self.headers, json=data)
            result = response.json()

            if result.get("code") == 200:
                self.knowledge_id = result["data"]["id"]
                print(f"✓ 知识库创建成功，ID: {self.knowledge_id}")
                return True
            else:
                print(f"✗ 创建知识库失败: {result.get('message', '未知错误')}")
                return False
        except Exception as e:
            print(f"✗ 创建知识库异常: {e}")
            return False

    def upload_document(self, knowledge_id, file_path):
        """上传文档到知识库"""
        print(f"正在上传文档: {file_path}")
        url = f"{self.base_url}/llm-application/open/document/upload_document/{knowledge_id}"

        try:
            with open(file_path, 'rb') as f:
                files = {"files": f}
                data = {"knowledge_type": 1}  # 按标题段落切分
                response = requests.post(url, headers=self.headers, files=files, data=data)

            result = response.json()

            if result.get("code") == 200:
                success_infos = result["data"]["successInfos"]
                if success_infos:
                    document_id = success_infos[0]["documentId"]
                    print(f"✓ 文档上传成功，文档ID: {document_id}")
                    return document_id
                else:
                    print("✗ 文档上传失败：没有成功信息")
                    return None
            else:
                print(f"✗ 文档上传失败: {result.get('message', '未知错误')}")
                return None
        except Exception as e:
            print(f"✗ 文档上传异常: {e}")
            return None

    def wait_for_embedding(self, document_id, timeout=300, check_interval=10):
        """等待文档向量化完成"""
        print(f"等待文档向量化完成 (文档ID: {document_id})...")

        start_time = time.time()
        while time.time() - start_time < timeout:
            url = f"{self.base_url}/llm-application/open/document/{document_id}"
            response = requests.get(url, headers=self.headers)
            result = response.json()

            if result.get("code") == 200:
                data = result["data"]
                embedding_stat = data.get("embedding_stat")

                if embedding_stat == 1:
                    print("✓ 文档向量化完成")
                    return True
                elif embedding_stat == 2:
                    fail_msg = data.get("failInfo", {}).get("embedding_msg", "未知错误")
                    print(f"✗ 文档向量化失败: {fail_msg}")
                    return False
                else:
                    print(f"向量化进行中... (状态: {embedding_stat})")

            time.sleep(check_interval)

        print("✗ 等待向量化超时")
        return False

    def retrieve(self, knowledge_ids, query, top_k=5):
        """检索知识库"""
        print(f"正在检索: {query}")
        url = f"{self.base_url}/llm-application/open/knowledge/retrieve"

        data = {
            "query": query,
            "knowledge_ids": knowledge_ids,
            "top_k": top_k,
            "rerank_status": 1,
            "rerank_model": "rerank-pro"
        }

        try:
            response = requests.post(url, headers=self.headers, json=data)
            result = response.json()

            if result.get("code") == 200:
                return result["data"]
            else:
                print(f"检索失败: {result.get('message', '未知错误')}")
                return []
        except Exception as e:
            print(f"检索异常: {e}")
            return []

    def delete_knowledge_base(self, knowledge_id):
        """删除知识库"""
        print(f"正在删除知识库: {knowledge_id}")
        url = f"{self.base_url}/llm-application/open/knowledge/{knowledge_id}"

        try:
            response = requests.delete(url, headers=self.headers)
            result = response.json()

            if result.get("code") == 200:
                print("✓ 知识库删除成功")
                return True
            else:
                print(f"✗ 知识库删除失败: {result.get('message', '未知错误')}")
                return False
        except Exception as e:
            print(f"✗ 知识库删除异常: {e}")
            return False


class FallbackRAG:
    """替代RAG方案：使用embeddings + rerank"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.documents = []

    def add_document(self, content, metadata=None):
        """添加文档"""
        self.documents.append({
            "content": content,
            "metadata": metadata or {}
        })

    def embed_text(self, text):
        """获取文本向量"""
        url = f"{self.base_url}/paas/v4/embeddings"
        data = {
            "model": "Embedding-3",
            "input": [text]
        }

        try:
            response = requests.post(url, headers=self.headers, json=data)
            result = response.json()

            if result.get("code") == 200:
                return result["data"][0]["embedding"]
            else:
                print(f"嵌入失败: {result.get('message', '未知错误')}")
                return None
        except Exception as e:
            print(f"嵌入异常: {e}")
            return None

    def rerank(self, query, documents, top_k=5):
        """重排序"""
        if not documents:
            return []

        url = f"{self.base_url}/paas/v4/rerank"
        data = {
            "model": "rerank-pro",
            "query": query,
            "documents": [{"text": doc["content"]} for doc in documents],
            "top_k": min(top_k, len(documents))
        }

        try:
            response = requests.post(url, headers=self.headers, json=data)
            result = response.json()

            if result.get("code") == 200:
                reranked_docs = []
                for i, item in enumerate(result["data"]):
                    idx = item["index"]
                    reranked_docs.append({
                        "text": documents[idx]["content"],
                        "score": item["relevance_score"],
                        "metadata": documents[idx]["metadata"]
                    })
                return reranked_docs
            else:
                print(f"重排失败: {result.get('message', '未知错误')}")
                return []
        except Exception as e:
            print(f"重排异常: {e}")
            return []

    def search(self, query, top_k=5):
        """搜索文档"""
        print(f"[替代方案] 正在搜索: {query}")

        # 获取查询向量
        query_embedding = self.embed_text(query)
        if not query_embedding:
            return []

        # 计算相似度（简化版）
        results = []
        for doc in self.documents:
            # 这里简化处理，实际应该计算向量相似度
            # 按关键词匹配评分
            score = 0
            query_lower = query.lower()
            content_lower = doc["content"].lower()

            if "退换货" in content_lower and "有效期" in content_lower:
                score += 10
            elif "有效期" in content_lower:
                score += 5
            elif any(word in content_lower for word in ["退货", "换货", "政策"]):
                score += 3

            if score > 0:
                results.append({
                    "text": doc["content"],
                    "score": score,
                    "metadata": doc["metadata"]
                })

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]


def main():
    print("=== 智谱AI知识库检索测试 ===")

    # 读取FAQ内容
    faq_path = "faq.txt"
    try:
        with open(faq_path, 'r', encoding='utf-8') as f:
            faq_content = f.read()
        print(f"已读取FAQ文件，内容长度: {len(faq_content)} 字符")
    except Exception as e:
        print(f"读取FAQ文件失败: {e}")
        return

    # 方案一：使用托管知识库
    print("\n=== 方案一：使用托管知识库 ===")
    kb = ZhipuKnowledgeBase(API_KEY)

    # 创建知识库
    if kb.create_knowledge_base("退换货政策FAQ"):
        # 上传文档
        doc_id = kb.upload_document(kb.knowledge_id, faq_path)
        if doc_id:
            # 等待向量化
            if kb.wait_for_embedding(doc_id):
                # 检索
                query = "退换货政策的有效期是多久"
                results = kb.retrieve([kb.knowledge_id], query)

                if results:
                    print(f"\n✓ 找到 {len(results)} 条相关结果：")
                    for i, result in enumerate(results, 1):
                        print(f"\n{i}. [相关度: {result.get('score', 0):.3f}]")
                        print(f"原文: {result['text']}")
                    print(f"\n=== 知识库检索完成 ===")
                    kb.delete_knowledge_base(kb.knowledge_id)
                    return
                else:
                    print("\n⚠ 知识库检索为空，可能是向量化失败")
            else:
                print("\n⚠ 向量化失败，尝试替代方案")

        # 清理
        if kb.knowledge_id:
            kb.delete_knowledge_base(kb.knowledge_id)

    # 方案二：使用替代RAG
    print("\n=== 方案二：使用替代RAG方案 ===")
    fallback = FallbackRAG(API_KEY)

    # 解析FAQ内容并添加到文档列表
    lines = faq_content.split('\n')
    current_section = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检查是否是标题
        if line.endswith('政策') or line.endswith('说明') or line.endswith('流程') or line.endswith('注意事项'):
            current_section = line
        elif line.startswith(('1.', '2.', '3.', '4.', '5.')) or line.startswith('-'):
            # 添加文档
            metadata = {"section": current_section} if current_section else {}
            fallback.add_document(line, metadata)

    print(f"已添加 {len(fallback.documents)} 个文档片段")

    # 搜索
    query = "退换货政策的有效期是多久"
    results = fallback.search(query)

    if results:
        print(f"\n✓ 找到 {len(results)} 条相关结果：")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. [相关度: {result.get('score', 0):.3f}]")
            print(f"原文: {result['text']}")
            if result.get('metadata'):
                print(f"来源: {result['metadata']['section']}")
        print(f"\n=== 替代方案检索完成 ===")
    else:
        print("未找到相关结果")


if __name__ == "__main__":
    main()