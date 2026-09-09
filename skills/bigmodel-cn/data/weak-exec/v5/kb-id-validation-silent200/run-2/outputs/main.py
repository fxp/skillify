#!/usr/bin/env python3
"""
智谱托管知识库 ID 验证脚本
用于验证配置中的知识库 ID 是否存在且可用
"""

import os
import sys
import requests
import json
from typing import Dict, Any, Optional


def get_env_variable(var_name: str) -> str:
    """获取环境变量，如果不存在则报错"""
    value = os.environ.get(var_name)
    if not value:
        print(f"❌ 错误：环境变量 {var_name} 未设置", file=sys.stderr)
        sys.exit(1)
    return value


def validate_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库是否存在且可用

    Args:
        kb_id: 知识库 ID
        api_key: 智谱 API Key

    Returns:
        dict: 验证结果，包含 status, message, data 等字段
    """
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建知识库详情 API URL
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    try:
        # 发送 GET 请求获取知识库详情
        print(f"🔍 正在验证知识库 ID: {kb_id}")
        print(f"📡 请求地址: {url}")

        response = requests.get(url, headers=headers, timeout=30)

        # 根据响应状态码判断结果
        if response.status_code == 200:
            try:
                data = response.json()
                # 检查响应格式是否正确
                if "code" in data and data["code"] == 200:
                    if "data" in data and data["data"]:
                        # 知识库存在且可用
                        kb_info = data["data"]
                        return {
                            "status": "valid",
                            "message": "✅ 知识库存在且可用",
                            "data": kb_info
                        }
                    else:
                        return {
                            "status": "invalid",
                            "message": "❌ API 返回格式异常，data 字段为空",
                            "raw_response": data
                        }
                else:
                    return {
                        "status": "invalid",
                        "message": f"❌ API 返回错误码: {data.get('code', 'unknown')}, 错误信息: {data.get('message', 'unknown')}",
                        "raw_response": data
                    }
            except json.JSONDecodeError:
                return {
                    "status": "invalid",
                    "message": "❌ API 返回非 JSON 格式数据",
                    "raw_response": response.text
                }
        elif response.status_code == 401:
            return {
                "status": "invalid",
                "message": "❌ API Key 无效或已过期",
                "http_status": response.status_code,
                "response_text": response.text
            }
        elif response.status_code == 404:
            return {
                "status": "invalid",
                "message": "❌ 知识库 ID 不存在",
                "http_status": response.status_code,
                "response_text": response.text
            }
        else:
            # 其他错误状态码
            try:
                error_data = response.json()
                error_msg = error_data.get('message', f'HTTP {response.status_code}')
            except json.JSONDecodeError:
                error_msg = f'HTTP {response.status_code}: {response.text[:200]}'

            return {
                "status": "invalid",
                "message": f"❌ API 请求失败: {error_msg}",
                "http_status": response.status_code,
                "raw_response": error_data if 'error_data' in locals() else response.text
            }

    except requests.exceptions.Timeout:
        return {
            "status": "invalid",
            "message": "❌ 请求超时（30秒）",
            "error_type": "timeout"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "invalid",
            "message": "❌ 无法连接到智谱AI服务器",
            "error_type": "connection_error"
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "invalid",
            "message": f"❌ 网络请求异常: {str(e)}",
            "error_type": "request_error"
        }


def print_validation_result(result: Dict[str, Any], kb_id: str) -> None:
    """打印验证结果"""
    print("\n" + "="*60)
    print("📋 知识库验证结果")
    print("="*60)

    if result["status"] == "valid":
        print(f"🟢 校验结论: 知识库有效")
        print(f"📝 知识库详情:")

        data = result["data"]
        print(f"  - ID: {data.get('id', kb_id)}")
        print(f"  - 名称: {data.get('name', '未知')}")
        print(f"  - 文档数量: {data.get('document_size', '未知')}")
        print(f"  - 总长度: {data.get('length', '未知')}")
        print(f"  - 总词数: {data.get('word_num', '未知')}")
        print(f"  - 上下文模式: {'启用' if data.get('contextual', 0) == 1 else '禁用'}")

    else:
        print(f"🔴 校验结论: 知识库无效")
        print(f"❌ 错误信息: {result['message']}")

        # 如果是网络连接问题，给出建议
        if result.get("error_type") == "connection_error":
            print("\n💡 建议:")
            print("  - 请检查网络连接是否正常")
            print("  - 如果使用代理，请确认代理配置正确")
        elif result.get("http_status") == 401:
            print("\n💡 建议:")
            print("  - 请检查 ZHIPUAI_API_KEY 是否正确")
            print("  - API Key 可能已过期，请重新获取")
        elif result.get("http_status") == 404:
            print("\n💡 建议:")
            print("  - 请检查 ZHIPU_KB_ID 是否正确")
            print("  - 知识库可能已被删除")
        elif result.get("error_type") == "timeout":
            print("\n💡 建议:")
            print("  - 网络响应较慢，请稍后重试")
            print("  - 检查网络是否稳定")


def main():
    """主函数"""
    print("🚀 开始验证智谱托管知识库...")

    # 获取环境变量
    try:
        kb_id = get_env_variable("ZHIPU_KB_ID")
        api_key = get_env_variable("ZHIPUAI_API_KEY")
    except SystemExit:
        return 1

    print(f"ℹ️  知识库 ID: {kb_id[:10]}...{kb_id[-4:] if len(kb_id) > 14 else kb_id}")
    print(f"ℹ️  API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else api_key}")
    print()

    # 执行验证
    result = validate_knowledge_base(kb_id, api_key)

    # 打印结果
    print_validation_result(result, kb_id)

    # 返回退出码：0 表示验证通过，1 表示验证失败
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)