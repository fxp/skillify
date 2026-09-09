#!/usr/bin/env python3
"""
智谱托管知识库 ID 校验脚本

用途：验证配置中的知识库 ID 是否存在且可用
环境变量：
- ZHIPU_KB_ID: 要验证的知识库 ID
- ZHIPUAI_API_KEY: 智谱 API Key

验证逻辑：
1. 调用知识库详情接口 GET /llm-application/open/knowledge/{id}
2. 根据 API 规范，HTTP 200 不代表成功，必须检查响应中的 code 字段
3. code=200 表示知识库存在且可用
4. code=100013 表示知识库不存在
5. 其他 code 值表示知识库不可用

输出：
- 明确打印验证结论
- 严格按照"宁可误报无效，也不能放坏 ID 上线"的原则
"""

import os
import requests
import json
from typing import Dict, Any


def validate_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库是否存在且可用

    Args:
        kb_id: 知识库 ID
        api_key: 智谱 API Key

    Returns:
        包含验证结果的字典：
        {
            "valid": bool,  # 知识库是否有效
            "error_code": int,  # 错误码（如果有）
            "error_message": str,  # 错误信息（如果有）
            "kb_name": str,  # 知识库名称（如果有）
            "document_count": int,  # 文档数量（如果有）
            "total_words": int,  # 总字数（如果有）
        }
    """
    # API 配置
    base_url = "https://open.bigmodel.cn/api"
    endpoint = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求参数
    params = {}

    try:
        # 发送请求
        print(f"正在验证知识库 ID: {kb_id}")
        print(f"请求地址: {endpoint}")
        resp = requests.get(endpoint, headers=headers, params=params, timeout=30)
        print(f"HTTP 状态码: {resp.status_code}")

        # 解析响应
        response_data = resp.json()
        print(f"完整响应: {json.dumps(response_data, indent=2, ensure_ascii=False)}")

        # 根据 API 规范，必须检查响应中的 code 字段
        # HTTP 200 不代表成功，真实结果在 code 字段中
        if "code" not in response_data:
            return {
                "valid": False,
                "error_code": -1,
                "error_message": "响应格式异常：缺少 code 字段",
                "kb_name": "",
                "document_count": 0,
                "total_words": 0,
            }

        error_code = response_data["code"]

        if error_code == 200:
            # 知识库存在且可用
            kb_data = response_data.get("data", {})
            return {
                "valid": True,
                "error_code": 0,
                "error_message": "",
                "kb_name": kb_data.get("name", ""),
                "document_count": kb_data.get("document_size", 0),
                "total_words": kb_data.get("word_num", 0),
            }
        else:
            # 知识库不可用，返回具体错误信息
            error_message = response_data.get("message", "未知错误")

            # 根据常见的错误码给出更友好的提示
            if error_code == 100013:
                error_message = "知识库不存在"
            elif error_code == 401:
                error_message = "API Key 无效或已过期"
            elif error_code == 403:
                error_message = "没有权限访问该知识库"
            elif error_code == 404:
                error_message = "资源不存在"

            return {
                "valid": False,
                "error_code": error_code,
                "error_message": error_message,
                "kb_name": "",
                "document_count": 0,
                "total_words": 0,
            }

    except requests.exceptions.Timeout:
        return {
            "valid": False,
            "error_code": -2,
            "error_message": "请求超时",
            "kb_name": "",
            "document_count": 0,
            "total_words": 0,
        }
    except requests.exceptions.ConnectionError:
        return {
            "valid": False,
            "error_code": -3,
            "error_message": "连接失败，请检查网络",
            "kb_name": "",
            "document_count": 0,
            "total_words": 0,
        }
    except json.JSONDecodeError:
        return {
            "valid": False,
            "error_code": -4,
            "error_message": "响应格式异常：无法解析 JSON",
            "kb_name": "",
            "document_count": 0,
            "total_words": 0,
        }
    except Exception as e:
        return {
            "valid": False,
            "error_code": -5,
            "error_message": f"未知错误: {str(e)}",
            "kb_name": "",
            "document_count": 0,
            "total_words": 0,
        }


def main():
    """主函数"""
    print("=" * 50)
    print("智谱托管知识库 ID 校验工具")
    print("=" * 50)

    # 从环境变量读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：未设置 ZHIPU_KB_ID 环境变量")
        print("请将要验证的知识库 ID 设置到环境变量 ZHIPU_KB_ID 中")
        return False

    if not api_key:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        print("请将智谱 API Key 设置到环境变量 ZHIPUAI_API_KEY 中")
        return False

    print(f"知识库 ID: {kb_id}")
    print(f"API Key: {api_key[:10]}...{api_key[-10:]}" if len(api_key) > 20 else api_key)
    print()

    # 验证知识库
    result = validate_knowledge_base(kb_id, api_key)

    # 打印验证结果
    print("\n" + "=" * 50)
    print("验证结果:")
    print("=" * 50)

    if result["valid"]:
        print("✅ 验证通过：知识库存在且可用")
        if result["kb_name"]:
            print(f"   知识库名称: {result['kb_name']}")
        print(f"   文档数量: {result['document_count']}")
        if result["total_words"] > 0:
            print(f"   总字数: {result['total_words']}")
        print("\n🎉 该知识库 ID 可以安全上线！")
        return True
    else:
        print("❌ 验证失败：知识库不可用")
        print(f"   错误码: {result['error_code']}")
        print(f"   错误信息: {result['error_message']}")

        # 根据错误类型给出建议
        if result["error_code"] == 100013:
            print("\n💡 建议：")
            print("   - 请检查知识库 ID 是否正确")
            print("   - 确认该知识库是否已创建")
        elif result["error_code"] == 401:
            print("\n💡 建议：")
            print("   - 请检查 API Key 是否正确")
            print("   - 确认 API Key 是否已激活")
        elif result["error_code"] == 403:
            print("\n💡 建议：")
            print("   - 该 API Key 可能没有访问该知识库的权限")
        elif result["error_code"] < 0:
            print("\n💡 建议：")
            print("   - 请检查网络连接")
            print("   - 稍后重试")
        else:
            print("\n💡 建议：")
            print("   - 请检查 API Key 权限")
            print("   - 联系智谱技术支持")

        print(f"\n⚠️  该知识库 ID 不能上线！")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)