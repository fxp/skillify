#!/usr/bin/env python3
"""
智谱AI托管知识库ID验证脚本
用于验证配置中的知识库ID是否存在且可用，作为发布流水线的校验步骤

使用方法：
python3 main.py
"""

import os
import sys
import requests
from typing import Dict, Any, Optional


def get_environment_variables() -> tuple[str, str]:
    """从环境变量读取配置"""
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

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
        api_key: 智谱AI API Key

    Returns:
        包含验证结果的字典：
        - valid: bool，知识库是否有效
        - message: str，验证结果信息
        - details: dict，API返回的详细信息
        - http_status: int，HTTP状态码
        - api_code: int，API返回的code字段
    """
    base_url = "https://open.bigmodel.cn/api"
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"🔍 正在验证知识库 ID: {kb_id}")
    print(f"🌐 请求地址: {url}")

    try:
        # 发起请求
        response = requests.get(url, headers=headers, timeout=30)

        # 记录HTTP状态码
        http_status = response.status_code

        # 解析响应
        try:
            response_data = response.json()
        except ValueError:
            # 如果响应不是有效的JSON
            return {
                'valid': False,
                'message': f'❌ API返回非JSON响应，HTTP状态码: {http_status}',
                'details': {'response_text': response.text[:500]},
                'http_status': http_status,
                'api_code': None
            }

        # 根据参考资料，知识库API的错误情况：
        # 1. HTTP状态码可能是200，但响应体code字段不是200
        # 2. 需要检查code字段而不是HTTP状态码
        api_code = response_data.get('code')

        if http_status != 200:
            # HTTP状态码不是200，直接判定失败
            return {
                'valid': False,
                'message': f'❌ HTTP请求失败，状态码: {http_status}',
                'details': response_data,
                'http_status': http_status,
                'api_code': api_code
            }

        if api_code != 200:
            # HTTP状态码是200，但API的code字段不是200
            error_message = response_data.get('message', '未知错误')
            if api_code == 100013:
                error_message = "知识库不存在"
            elif api_code == 401:
                error_message = "API Key无效或已过期"
            elif api_code == 403:
                error_message = "没有权限访问该知识库"

            return {
                'valid': False,
                'message': f'❌ 知识库验证失败 (code: {api_code}): {error_message}',
                'details': response_data,
                'http_status': http_status,
                'api_code': api_code
            }

        # 验证成功，获取知识库详情
        knowledge_data = response_data.get('data', {})
        kb_name = knowledge_data.get('name', '未命名知识库')
        document_count = knowledge_data.get('document_size', 0)
        total_length = knowledge_data.get('length', 0)

        return {
            'valid': True,
            'message': f'✅ 知识库验证成功',
            'details': {
                'name': kb_name,
                'document_count': document_count,
                'total_length': total_length,
                'embedding_id': knowledge_data.get('embedding_id'),
                'contextual': knowledge_data.get('contextual'),
                'background': knowledge_data.get('background'),
                'icon': knowledge_data.get('icon')
            },
            'http_status': http_status,
            'api_code': api_code
        }

    except requests.exceptions.Timeout:
        return {
            'valid': False,
            'message': '❌ 请求超时（30秒）',
            'details': {},
            'http_status': None,
            'api_code': None
        }
    except requests.exceptions.ConnectionError:
        return {
            'valid': False,
            'message': '❌ 无法连接到智谱API服务器',
            'details': {},
            'http_status': None,
            'api_code': None
        }
    except Exception as e:
        return {
            'valid': False,
            'message': f'❌ 验证过程中发生未知错误: {str(e)}',
            'details': {},
            'http_status': None,
            'api_code': None
        }


def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI托管知识库ID验证工具")
    print("=" * 60)

    # 获取环境变量
    kb_id, api_key = get_environment_variables()

    # 隐藏API Key的部分显示
    masked_key = api_key[:8] + "*" * (len(api_key) - 8) if len(api_key) > 8 else "*" * len(api_key)
    print(f"🔑 API Key: {masked_key}")
    print(f"📚 知识库ID: {kb_id}")
    print()

    # 验证知识库
    result = validate_knowledge_base(kb_id, api_key)

    # 输出结果
    print("\n" + "=" * 60)
    print("验证结果:")
    print("=" * 60)

    if result['valid']:
        print(f"✅ {result['message']}")
        print(f"\n📋 知识库详情:")
        print(f"   - 名称: {result['details']['name']}")
        print(f"   - 文档数量: {result['details']['document_count']}")
        print(f"   - 总长度: {result['details']['total_length']:,} 字符")
        print(f"   - 向量化模型ID: {result['details']['embedding_id']}")
        print(f"   - 上下文增强: {'是' if result['details']['contextual'] else '否'}")
        print(f"   - 背景颜色: {result['details']['background']}")
        print(f"   - 图标: {result['details']['icon']}")

        print(f"\n📊 网络请求信息:")
        print(f"   - HTTP状态码: {result['http_status']}")
        print(f"   - API响应码: {result['api_code']}")

        print("\n🎉 知识库验证通过，可以安全上线！")
        sys.exit(0)
    else:
        print(f"❌ {result['message']}")

        if result.get('api_code'):
            print(f"\n📊 网络请求信息:")
            print(f"   - HTTP状态码: {result['http_status']}")
            print(f"   - API响应码: {result['api_code']}")

        if result.get('details') and result['details']:
            print(f"\n🔍 详细信息:")
            for key, value in result['details'].items():
                if key not in ['http_status', 'api_code']:
                    print(f"   - {key}: {value}")

        print("\n🚨 知识库验证失败，阻止上线！")
        sys.exit(1)


if __name__ == "__main__":
    main()