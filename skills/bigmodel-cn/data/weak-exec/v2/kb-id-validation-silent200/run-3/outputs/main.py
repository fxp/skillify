#!/usr/bin/env python3
"""
智谱托管知识库ID校验脚本
用途：验证配置的知识库ID是否存在且可用
环境变量：
- ZHIPU_KB_ID: 需要校验的知识库ID
- ZHIPUAI_API_KEY: 智谱AI API Key
"""

import os
import sys
import requests

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
VERIFY_ENDPOINT = f"{BASE_URL}/llm-application/open/knowledge"

def validate_knowledge_base(kb_id, api_key):
    """
    验证知识库是否存在且可用

    Args:
        kb_id (str): 知识库ID
        api_key (str): 智谱AI API Key

    Returns:
        bool: 知识库是否有效
    """
    print(f"开始验证知识库ID: {kb_id}")

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 调用知识库详情接口
        response = requests.get(
            f"{VERIFY_ENDPOINT}/{kb_id}",
            headers=headers,
            timeout=10
        )

        # 解析响应
        response_data = response.json()

        # 根据接入说明书：知识库接口HTTP状态码永远是200，真实状态在response['code']
        if response.status_code != 200:
            print(f"❌ 接口HTTP状态码异常: {response.status_code}")
            return False

        # 检查业务状态码
        if response_data.get("code") == 200:
            # 知识库存在
            kb_info = response_data.get("data", {})
            name = kb_info.get("name", "未知名称")
            doc_count = kb_info.get("document_size", 0)

            print(f"✅ 知识库验证成功")
            print(f"   - 知识库名称: {name}")
            print(f"   - 文档数量: {doc_count}")
            return True

        elif response_data.get("code") == 100013:
            # 知识库不存在
            print(f"❌ 知识库不存在 (code: 100013)")
            return False

        else:
            # 其他错误码
            error_code = response_data.get("code", "未知错误码")
            error_msg = response_data.get("message", "未知错误")
            print(f"❌ 知识库验证失败 (code: {error_code})")
            print(f"   错误信息: {error_msg}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 解析响应异常: {str(e)}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("智谱托管知识库ID校验工具")
    print("=" * 50)

    # 从环境变量读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("❌ 错误: 未设置环境变量 ZHIPU_KB_ID")
        sys.exit(1)

    if not api_key:
        print("❌ 错误: 未设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    print(f"从环境变量读取到配置:")
    print(f"   - ZHIPU_KB_ID: {kb_id}")
    print(f"   - ZHIPUAI_API_KEY: {'*' * (len(api_key) - 4)}{api_key[-4:]}")

    # 执行验证
    is_valid = validate_knowledge_base(kb_id, api_key)

    # 输出最终结论
    print("\n" + "=" * 50)
    print("校验结论:")
    print("=" * 50)

    if is_valid:
        print("✅ 校验通过: 知识库存在且可用")
        sys.exit(0)
    else:
        print("❌ 校验失败: 知识库不存在或不可用")
        sys.exit(1)

if __name__ == "__main__":
    main()