#!/usr/bin/env python3
"""
智谱托管知识库ID校验脚本

用于验证配置中的知识库ID是否存在且可用，作为发布流水线的卡点。
宁可误报无效，也不能放坏ID上线。

环境变量要求：
- ZHIPU_KB_ID: 要验证的知识库ID
- ZHIPUAI_API_KEY: 智谱AI API Key
"""

import os
import sys
import requests
from typing import Dict, Any


def validate_knowledge_base() -> Dict[str, Any]:
    """
    验证知识库是否存在且可用

    Returns:
        dict: 包含验证结果和详细信息的字典
    """
    # 从环境变量读取配置
    kb_id = os.getenv('ZHIPU_KB_ID')
    api_key = os.getenv('ZHIPUAI_API_KEY')

    # 验证环境变量是否存在
    if not kb_id:
        return {
            'valid': False,
            'reason': '环境变量 ZHIPU_KB_ID 未设置',
            'code': 'ENV_MISSING_KB_ID'
        }

    if not api_key:
        return {
            'valid': False,
            'reason': '环境变量 ZHIPUAI_API_KEY 未设置',
            'code': 'ENV_MISSING_API_KEY'
        }

    print(f"开始验证知识库ID: {kb_id}")

    # API配置
    base_url = "https://open.bigmodel.cn/api"
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发送请求
        print(f"发送请求到: {url}")
        response = requests.get(url, headers=headers, timeout=30)

        # 解析响应
        try:
            data = response.json()
        except ValueError:
            return {
                'valid': False,
                'reason': f'响应不是有效的JSON格式，HTTP状态码: {response.status_code}',
                'code': 'INVALID_JSON_RESPONSE',
                'http_status': response.status_code,
                'response_text': response.text[:200]  # 只显示前200个字符
            }

        # 重要：根据文档，知识库API即使在出错时也返回HTTP 200
        # 真正的成功/失败判断需要看响应体中的code字段
        http_status = response.status_code
        response_code = data.get('code')

        # 打印原始响应（调试用）
        print(f"HTTP状态码: {http_status}")
        print(f"响应体中的code: {response_code}")
        print(f"完整响应: {data}")

        # 验证知识库是否存在
        if response_code == 200:
            return {
                'valid': True,
                'reason': '知识库验证通过',
                'code': 'KB_EXISTS',
                'http_status': http_status,
                'response_code': response_code,
                'kb_info': {
                    'id': data.get('data', {}).get('id'),
                    'name': data.get('data', {}).get('name'),
                    'embedding_id': data.get('data', {}).get('embedding_id'),
                    'document_size': data.get('data', {}).get('document_size'),
                    'length': data.get('data', {}).get('length'),
                    'word_num': data.get('data', {}).get('word_num')
                }
            }
        else:
            # 知识库不存在的错误码
            error_codes = [100013]  # 知识库不存在
            if response_code in error_codes:
                return {
                    'valid': False,
                    'reason': f'知识库不存在（错误码: {response_code}）',
                    'code': 'KB_NOT_EXISTS',
                    'http_status': http_status,
                    'response_code': response_code,
                    'error_message': data.get('message', '')
                }
            else:
                # 其他错误码
                return {
                    'valid': False,
                    'reason': f'知识库验证失败（错误码: {response_code}）',
                    'code': 'KB_VALIDATION_FAILED',
                    'http_status': http_status,
                    'response_code': response_code,
                    'error_message': data.get('message', '')
                }

    except requests.exceptions.Timeout:
        return {
            'valid': False,
            'reason': '请求超时，无法验证知识库',
            'code': 'REQUEST_TIMEOUT',
            'http_status': None,
            'response_code': None
        }

    except requests.exceptions.ConnectionError:
        return {
            'valid': False,
            'reason': '网络连接错误，无法连接到智谱API',
            'code': 'CONNECTION_ERROR',
            'http_status': None,
            'response_code': None
        }

    except requests.exceptions.RequestException as e:
        return {
            'valid': False,
            'reason': f'请求异常: {str(e)}',
            'code': 'REQUEST_EXCEPTION',
            'http_status': None,
            'response_code': None
        }

    except Exception as e:
        return {
            'valid': False,
            'reason': f'未知错误: {str(e)}',
            'code': 'UNKNOWN_ERROR',
            'http_status': None,
            'response_code': None
        }


def print_validation_result(result: Dict[str, Any]) -> None:
    """
    打印验证结果

    Args:
        result: 验证结果字典
    """
    print("\n" + "="*50)
    print("知识库校验结果")
    print("="*50)

    if result['valid']:
        print("✅ 结论: 知识库有效")
        print(f"原因: {result['reason']}")

        if 'kb_info' in result:
            info = result['kb_info']
            print(f"\n知识库详情:")
            print(f"  ID: {info.get('id', 'N/A')}")
            print(f"  名称: {info.get('name', 'N/A')}")
            print(f"  向量化模型ID: {info.get('embedding_id', 'N/A')}")
            print(f"  文档数量: {info.get('document_size', 'N/A')}")
            print(f"  分词后长度: {info.get('length', 'N/A')}")
            print(f"  字数: {info.get('word_num', 'N/A')}")

        print(f"\n接口信息:")
        print(f"  HTTP状态码: {result.get('http_status', 'N/A')}")
        print(f"  响应code: {result.get('response_code', 'N/A')}")

    else:
        print("❌ 结论: 知识库无效")
        print(f"原因: {result['reason']}")

        if result.get('http_status'):
            print(f"\n接口信息:")
            print(f"  HTTP状态码: {result['http_status']}")

        if result.get('response_code'):
            print(f"  响应code: {result['response_code']}")
            if result.get('error_message'):
                print(f"  错误信息: {result['error_message']}")

        print(f"\n错误代码: {result['code']}")


def main():
    """主函数"""
    print("智谱托管知识库校验脚本")
    print("="*50)

    # 执行验证
    result = validate_knowledge_base()

    # 打印结果
    print_validation_result(result)

    # 输出脚本返回值（供CI/CD使用）
    # 0表示成功，1表示失败
    sys.exit(0 if result['valid'] else 1)


if __name__ == "__main__":
    main()