#!/usr/bin/env python3
"""
智谱AI托管知识库ID校验脚本

用途：验证环境变量 ZHIPU_KB_ID 中的知识库ID是否存在且可用
特性：
- 严格校验：宁可误报无效，绝不放行无效ID
- 只能验证知识库存在性，不验证文档状态（因为上传成功≠文档可检索）
- API Key 从环境变量 ZHIPUAI_API_KEY 读取
- 使用 requests 库，兼容性良好

输出：
- 打印明确的校验结论
- 返回码：0=有效，1=无效
"""

import os
import sys
import requests
from typing import Dict, Any


def validate_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库是否存在且可用

    Args:
        kb_id: 知识库ID
        api_key: 智谱AI API Key

    Returns:
        Dict: 包含验证结果和详细信息
    """
    # 设置API端点
    base_url = "https://open.bigmodel.cn/api"
    endpoint = f"/llm-application/open/knowledge/{kb_id}"

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"🔍 正在验证知识库ID: {kb_id}")
    print(f"🌐 请求地址: {base_url}{endpoint}")

    try:
        # 发送GET请求获取知识库详情
        response = requests.get(
            f"{base_url}{endpoint}",
            headers=headers,
            timeout=30  # 30秒超时
        )

        # 解析响应
        try:
            resp_data = response.json()
        except ValueError:
            # 如果不是JSON响应
            return {
                "valid": False,
                "reason": f"服务器返回非JSON响应: {response.text[:200]}...",
                "status_code": response.status_code,
                "error_type": "invalid_response"
            }

        # 关键检查：即使HTTP状态码是200，也要检查响应体中的code字段
        # 文档说明：知识库API出错时HTTP状态码依然是200，真实结果在响应体的code里
        if response.status_code == 200:
            if resp_data.get("code") == 200:
                # 知识库存在且正常
                kb_info = resp_data.get("data", {})
                kb_name = kb_info.get("name", "未知名称")

                return {
                    "valid": True,
                    "reason": f"知识库验证成功",
                    "knowledge_base_name": kb_name,
                    "embedding_id": kb_info.get("embedding_id"),
                    "document_size": kb_info.get("document_size", 0),
                    "length": kb_info.get("length", 0),
                    "word_num": kb_info.get("word_num", 0),
                    "status_code": response.status_code,
                    "api_code": resp_data.get("code")
                }
            else:
                # API返回业务错误
                error_msg = resp_data.get("message", "未知错误")
                error_code = resp_data.get("code", "unknown")

                return {
                    "valid": False,
                    "reason": f"知识库不存在或不可用 (API错误码: {error_code})",
                    "error_message": error_msg,
                    "error_code": error_code,
                    "status_code": response.status_code,
                    "api_code": resp_data.get("code"),
                    "error_type": "api_error"
                }
        else:
            # HTTP状态码非200
            error_msg = resp_data.get("message", f"HTTP {response.status_code} 错误")

            return {
                "valid": False,
                "reason": f"HTTP请求失败: {response.status_code}",
                "error_message": error_msg,
                "status_code": response.status_code,
                "error_type": "http_error"
            }

    except requests.exceptions.Timeout:
        return {
            "valid": False,
            "reason": "请求超时（30秒）",
            "error_type": "timeout"
        }
    except requests.exceptions.ConnectionError:
        return {
            "valid": False,
            "reason": "网络连接失败",
            "error_type": "connection_error"
        }
    except requests.exceptions.RequestException as e:
        return {
            "valid": False,
            "reason": f"请求异常: {str(e)}",
            "error_type": "request_error"
        }
    except Exception as e:
        return {
            "valid": False,
            "reason": f"未知异常: {str(e)}",
            "error_type": "unknown_error"
        }


def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI托管知识库ID校验工具")
    print("=" * 60)

    # 读取环境变量
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查必要的环境变量
    if not kb_id:
        print("❌ 错误：未找到环境变量 ZHIPU_KB_ID")
        print("请设置要验证的知识库ID：export ZHIPU_KB_ID='your_knowledge_base_id'")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：未找到环境变量 ZHIPUAI_API_KEY")
        print("请设置API Key：export ZHIPUAI_API_KEY='your_api_key'")
        sys.exit(1)

    # 打印基本信息（不包含敏感信息）
    print(f"📝 知识库ID: {kb_id}")
    print(f"🔑 API Key: {'*' * (len(api_key) - 4) + api_key[-4:]} (已隐藏)")
    print()

    # 执行验证
    result = validate_knowledge_base(kb_id, api_key)

    # 输出结果
    print("\n" + "=" * 60)
    print("📊 验证结果")
    print("=" * 60)

    if result["valid"]:
        print("✅ 知识库验证通过")
        print(f"📚 知识库名称: {result['knowledge_base_name']}")
        print(f"🔧 向量化模型ID: {result['embedding_id']}")
        print(f"📄 文档数量: {result['document_size']}")
        print(f"📝 总长度: {result['length']} 字符")
        print(f"🔤 总字数: {result['word_num']}")
        print(f"🌐 HTTP状态码: {result['status_code']}")
        print(f"📋 API返回码: {result['api_code']}")
        print("\n🎉 知识库状态良好，可以上线使用！")
        sys.exit(0)
    else:
        print("❌ 知识库验证失败")
        print(f"❌ 失败原因: {result['reason']}")

        if "error_message" in result:
            print(f"❌ 错误详情: {result['error_message']}")

        if "error_code" in result:
            print(f"❌ 错误代码: {result['error_code']}")

        if "error_type" in result:
            print(f"❌ 错误类型: {result['error_type']}")

        print("\n🚨 知识库存在问题，请勿上线！")
        sys.exit(1)


if __name__ == "__main__":
    main()