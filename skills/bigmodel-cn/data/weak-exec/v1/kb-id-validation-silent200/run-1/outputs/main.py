#!/usr/bin/env python3
"""
智谱托管知识库ID验证脚本

用于验证配置中的知识库ID是否存在且可用。这个脚本会作为发布流水线的卡点，
确保不会将无效的知识库ID上线。

特点：
- 宁可误报无效，也不放坏ID上线
- 明确打印验证结论
- 从环境变量读取配置
"""

import os
import requests
import json
import sys
from typing import Dict, Any, Optional


def get_env_variables() -> tuple[str, str]:
    """获取环境变量"""
    kb_id = os.getenv('ZHIPU_KB_ID')
    api_key = os.getenv('ZHIPUAI_API_KEY')

    if not kb_id:
        print("❌ 错误：环境变量 ZHIPU_KB_ID 未设置")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：环境变量 ZHIPUAI_API_KEY 未设置")
        sys.exit(1)

    return kb_id, api_key


def validate_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库是否存在且可用

    Args:
        kb_id: 知识库ID
        api_key: API Key

    Returns:
        API响应结果
    """
    # API endpoint
    url = f"https://open.bigmodel.cn/api/llm-application/open/knowledge/{kb_id}"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=30)

        # 根据文档，知识库API即使出错也返回200状态码，需要检查响应体中的code
        result = response.json()

        return {
            'status_code': response.status_code,
            'response': result,
            'success': result.get('code') == 200
        }

    except requests.exceptions.RequestException as e:
        return {
            'status_code': None,
            'response': {'error': str(e)},
            'success': False,
            'error_type': 'network_error'
        }
    except json.JSONDecodeError as e:
        return {
            'status_code': None,
            'response': {'error': f'JSON解析失败: {str(e)}'},
            'success': False,
            'error_type': 'json_error'
        }


def print_validation_result(kb_id: str, validation_result: Dict[str, Any]) -> None:
    """打印验证结果"""
    print("\n" + "="*50)
    print(f"知识库ID验证结果")
    print("="*50)
    print(f"知识库ID: {kb_id}")

    if validation_result['success']:
        response = validation_result['response']
        data = response.get('data', {})

        print(f"✅ 验证结果: 有效")
        print(f"状态码: {validation_result['status_code']}")
        print(f"API返回码: {response.get('code')}")
        print(f"知识库名称: {data.get('name', '未知')}")
        print(f"向量化模型: {data.get('embedding_model', '未知')}")
        print(f"文档数量: {data.get('document_size', 0)}")
        print(f"总字数: {data.get('word_num', 0)}")
        print(f"是否启用上下文增强: {'是' if data.get('contextual', 0) == 1 else '否'}")

        # 检查知识库是否为空
        doc_size = data.get('document_size', 0)
        if doc_size == 0:
            print("⚠️  警告: 该知识库没有文档，可能无法提供有效的检索结果")

        print(f"\n🎉 结论: 知识库存在且可用，可以通过验证")

    else:
        response = validation_result['response']
        error_type = validation_result.get('error_type', 'api_error')

        print(f"❌ 验证结果: 无效")
        print(f"状态码: {validation_result['status_code']}")

        if error_type == 'network_error':
            print(f"网络错误: {response.get('error')}")
            print(f"\n❌ 结论: 网络连接失败，无法验证知识库，为了确保线上环境可用，判定为无效")

        elif error_type == 'json_error':
            print(f"数据解析错误: {response.get('error')}")
            print(f"\n❌ 结论: API响应格式异常，无法验证知识库，为了确保线上环境可用，判定为无效")

        else:
            # API层面的错误
            api_code = response.get('code', 'unknown')
            api_message = response.get('message', '未知错误')

            print(f"API返回码: {api_code}")
            print(f"错误信息: {api_message}")

            # 根据常见错误码给出更具体的说明
            if api_code == 100013:
                print(f"具体错误: 知识库不存在")
            elif api_code == 401:
                print(f"具体错误: API Key无效或已过期")
            elif api_code == 403:
                print(f"具体错误: 没有权限访问该知识库")
            elif api_code == 429:
                print(f"具体错误: 请求过于频繁，请稍后重试")

            print(f"\n❌ 结论: 知识库不存在或无法访问，验证失败")

    print("="*50)


def main():
    """主函数"""
    print("🔍 开始验证智谱托管知识库ID...")

    # 获取环境变量
    kb_id, api_key = get_env_variables()

    print(f"📋 配置信息:")
    print(f"   知识库ID: {kb_id[:10]}...{kb_id[-10:] if len(kb_id) > 20 else kb_id}")
    print(f"   API Key: {'*' * 30}{api_key[-4:] if len(api_key) > 30 else api_key}")

    # 验证知识库
    validation_result = validate_knowledge_base(kb_id, api_key)

    # 打印结果
    print_validation_result(kb_id, validation_result)

    # 根据验证结果设置退出码
    # 0: 成功，1: 失败
    sys.exit(0 if validation_result['success'] else 1)


if __name__ == "__main__":
    main()