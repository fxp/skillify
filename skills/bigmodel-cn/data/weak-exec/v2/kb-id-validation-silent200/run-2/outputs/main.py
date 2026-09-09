#!/usr/bin/env python3
"""
智谱托管知识库 ID 校验脚本

用途：验证配置中的知识库 ID 是否存在且可用
环境变量：
- ZHIPU_KB_ID: 要验证的知识库 ID
- ZHIPUAI_API_KEY: 智谱 AI API Key

重要：宁可误报无效，也不能放一个坏 ID 上线
"""

import os
import sys
import requests


def validate_knowledge_base():
    """验证知识库是否存在且可用"""

    # 从环境变量读取配置
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        return False

    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False

    # API 基础配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 知识库详情接口
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    try:
        # 1. 首先验证知识库是否存在
        print(f"🔍 正在验证知识库 ID: {kb_id}")
        resp = requests.get(url, headers=headers)

        # ⚠️ 重要：知识库接口 HTTP 状态码永远是 200，真实状态在 resp.json()["code"]
        if resp.status_code != 200:
            print(f"❌ HTTP 状态码异常: {resp.status_code}")
            return False

        resp_data = resp.json()

        # 2. 检查响应中的 code 字段
        if resp_data.get("code") != 200:
            error_msg = resp_data.get("message", "未知错误")
            print(f"❌ 知识库验证失败: {error_msg}")
            if resp_data.get("code") == 100013:
                print("   错误代码 100013: 知识库不存在")
            return False

        # 3. 解析知识库信息
        kb_info = resp_data.get("data", {})
        kb_name = kb_info.get("name", "未知名称")
        kb_embedding_id = kb_info.get("embedding_id")

        # 获取向量化模型名称
        embedding_models = {
            3: "Embedding-2",
            11: "Embedding-3",
            12: "Embedding-3-pro"
        }
        embedding_model = embedding_models.get(kb_embedding_id, f"未知模型({kb_embedding_id})")

        print(f"✅ 知识库存在且可用")
        print(f"   知识库名称: {kb_name}")
        print(f"   向量化模型: {embedding_model}")
        print(f"   文档数量: {kb_info.get('document_size', 0)}")
        print(f"   总字数: {kb_info.get('word_num', 0)}")

        # 4. 额外验证：尝试检索（如果知识库没有文档，检索应该返回空数组但 code=200）
        retrieve_url = f"{base_url}/llm-application/open/knowledge/retrieve"
        retrieve_payload = {
            "query": "测试查询",
            "knowledge_ids": [kb_id],
            "top_k": 1
        }

        print(f"🔍 正在测试检索功能...")
        retrieve_resp = requests.post(retrieve_url, headers=headers, json=retrieve_payload)

        if retrieve_resp.status_code == 200:
            retrieve_data = retrieve_resp.json()
            if retrieve_data.get("code") == 200:
                # 检索正常，即使返回空数组也说明接口可用
                print("✅ 检索接口测试通过")
            else:
                error_msg = retrieve_data.get("message", "未知错误")
                print(f"❌ 检索接口异常: {error_msg}")
                return False
        else:
            print(f"❌ 检索接口 HTTP 状态码异常: {retrieve_resp.status_code}")
            return False

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {str(e)}")
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("智谱托管知识库 ID 校验")
    print("=" * 50)

    # 执行验证
    is_valid = validate_knowledge_base()

    # 输出最终结论
    print("\n" + "=" * 50)
    if is_valid:
        print("✅ 验证结论: 知识库有效，可以上线")
        print("   风险评估: 低 - 已通过存在性、可用性、检索功能测试")
        sys.exit(0)
    else:
        print("❌ 验证结论: 知识库无效，禁止上线")
        print("   风险评估: 高 - 可能导致生产环境功能异常")
        sys.exit(1)


if __name__ == "__main__":
    main()