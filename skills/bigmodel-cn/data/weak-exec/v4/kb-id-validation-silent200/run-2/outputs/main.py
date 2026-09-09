#!/usr/bin/env python3
"""
知识库 ID 校验脚本

用途：验证配置中存储的智谱托管知识库 ID 是否存在且可用
环境变量：
- ZHIPU_KB_ID: 要验证的知识库 ID
- ZHIPUAI_API_KEY: 智谱 API Key

输出：明确打印校验结论，绝对不能将无效 ID 报告为有效
"""

import os
import sys
import requests
from typing import Optional, Dict, Any

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
HEADERS = {"Content-Type": "application/json"}

def get_api_key() -> Optional[str]:
    """获取 API Key"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return None
    return api_key

def get_kb_id() -> Optional[str]:
    """获取知识库 ID"""
    kb_id = os.environ.get('ZHIPU_KB_ID')
    if not kb_id:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        return None
    return kb_id

def check_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库是否存在

    返回：
    - success: 是否验证成功
    - message: 验证结果消息
    - data: 知识库详情（如果存在）
    """
    url = f"{BASE_URL}/llm-application/open/knowledge/{kb_id}"
    headers = {**HEADERS, "Authorization": f"Bearer {api_key}"}

    try:
        # 验证知识库是否存在
        print(f"🔍 正在验证知识库 ID: {kb_id}")
        resp = requests.get(url, headers=headers)

        # 重要：知识库接口即使出错也返回 HTTP 200，需要检查响应体的 code
        if resp.status_code != 200:
            return {
                "success": False,
                "message": f"HTTP 状态码异常: {resp.status_code}",
                "data": None
            }

        resp_data = resp.json()

        # 检查业务错误码
        if resp_data.get("code") != 200:
            error_code = resp_data.get("code", "unknown")
            error_msg = resp_data.get("message", "未知错误")
            return {
                "success": False,
                "message": f"知识库无效 (错误码: {error_code}): {error_msg}",
                "data": None
            }

        # 知识库存在，获取详情
        kb_data = resp_data.get("data", {})
        kb_name = kb_data.get("name", "未命名")
        kb_doc_count = kb_data.get("document_size", 0)
        kb_length = kb_data.get("length", 0)
        kb_word_num = kb_data.get("word_num", 0)

        print(f"✅ 知识库存在: {kb_name}")
        print(f"   - ID: {kb_id}")
        print(f"   - 文档数量: {kb_doc_count}")
        print(f"   - 长度: {kb_length} 字")
        print(f"   - 字数: {kb_word_num}")

        # 如果有文档，进一步检查文档状态
        if kb_doc_count > 0:
            doc_check = check_documents(kb_id, api_key)
            if not doc_check["success"]:
                return doc_check

            # 计算可用文档数量
            available_docs = sum(1 for doc in doc_check["data"] if doc.get("embedding_stat") == 1)
            failed_docs = kb_doc_count - available_docs

            if failed_docs > 0:
                print(f"⚠️  警告: 有 {failed_docs} 个文档向量化失败")
                if available_docs > 0:
                    print(f"   但仍有 {available_docs} 个文档可用")
                else:
                    return {
                        "success": False,
                        "message": "知识库存在但没有可用的文档",
                        "data": kb_data
                    }
            else:
                print(f"✅ 所有 {kb_doc_count} 个文档都可用")

        return {
            "success": True,
            "message": f"知识库验证成功: {kb_name} (ID: {kb_id})",
            "data": kb_data
        }

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"网络请求失败: {str(e)}",
            "data": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"未知错误: {str(e)}",
            "data": None
        }

def check_documents(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    检查知识库中的文档状态

    返回：
    - success: 是否成功获取文档列表
    - message: 消息
    - data: 文档列表
    """
    url = f"{BASE_URL}/llm-application/open/document"
    headers = {**HEADERS, "Authorization": f"Bearer {api_key}"}
    params = {"knowledge_id": kb_id, "page": 1, "size": 100}  # 获取前100个文档

    try:
        resp = requests.get(url, headers=headers, params=params)

        if resp.status_code != 200:
            return {
                "success": False,
                "message": f"获取文档列表失败，HTTP状态码: {resp.status_code}",
                "data": []
            }

        resp_data = resp.json()

        if resp_data.get("code") != 200:
            error_code = resp_data.get("code", "unknown")
            error_msg = resp_data.get("message", "未知错误")
            return {
                "success": False,
                "message": f"获取文档列表失败 (错误码: {error_code}): {error_msg}",
                "data": []
            }

        documents = resp_data.get("data", {}).get("list", [])
        return {
            "success": True,
            "message": f"获取到 {len(documents)} 个文档",
            "data": documents
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"获取文档列表失败: {str(e)}",
            "data": []
        }

def main():
    """主函数"""
    print("=" * 60)
    print("智谱托管知识库 ID 校验工具")
    print("=" * 60)

    # 获取环境变量
    api_key = get_api_key()
    kb_id = get_kb_id()

    if not api_key or not kb_id:
        print("\n❌ 校验失败：缺少必要的环境变量")
        sys.exit(1)

    print(f"\n🔧 配置信息:")
    print(f"   - API Key: {'*' * 20 + api_key[-4:]}")
    print(f"   - 知识库 ID: {kb_id}")

    # 执行校验
    result = check_knowledge_base(kb_id, api_key)

    # 输出最终结论
    print("\n" + "=" * 60)
    print("校验结论:")
    print("=" * 60)

    if result["success"]:
        print("✅ 成功: 知识库存在且可用")
        print(f"   消息: {result['message']}")
        sys.exit(0)
    else:
        print("❌ 失败: 知识库无效或不可用")
        print(f"   原因: {result['message']}")
        sys.exit(1)

if __name__ == "__main__":
    main()