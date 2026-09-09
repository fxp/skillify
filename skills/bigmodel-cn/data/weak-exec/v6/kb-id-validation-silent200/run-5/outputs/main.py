#!/usr/bin/env python3
"""
智谱AI知识库ID验证脚本

用途：
验证配置的智谱托管知识库ID是否存在且可用。此脚本会挂到发布流水线上做卡点，
绝对不能把无效的说成有效——宁可误报无效，也不能放一个坏ID上线。

使用方法：
export ZHIPU_KB_ID=your_knowledge_base_id
export ZHIPUAI_API_KEY=your_api_key
python3 main.py
"""

import os
import sys
import requests

def validate_knowledge_base(kb_id, api_key):
    """
    验证知识库是否存在且可用

    Args:
        kb_id (str): 知识库ID
        api_key (str): 智谱AI API Key

    Returns:
        dict: 包含验证结果和详细信息的字典
    """
    # API基础配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 验证知识库详情
    validate_url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    try:
        # 重要提示：根据文档，这个接口出错时HTTP状态码依然是200，真实结果在响应体的code里
        response = requests.get(validate_url, headers=headers, timeout=30)
        response.raise_for_status()  # 检查HTTP状态码

        # 解析响应
        result = response.json()

        # 分析响应
        validation_result = {
            "kb_id": kb_id,
            "exists": False,
            "valid": False,
            "error": None,
            "details": {}
        }

        # 检查业务错误码
        if result.get("code") == 200:
            # 知识库存在
            validation_result["exists"] = True
            data = result.get("data", {})

            # 获取知识库基本信息
            validation_result["details"] = {
                "name": data.get("name"),
                "embedding_id": data.get("embedding_id"),
                "embedding_model": data.get("embedding_model"),
                "document_size": data.get("document_size", 0),
                "length": data.get("length", 0),
                "word_num": data.get("word_num", 0),
                "contextual": data.get("contextual", 0),
                "background": data.get("background"),
                "icon": data.get("icon")
            }

            # 验证知识库是否可用（是否有文档）
            validation_result["valid"] = data.get("document_size", 0) > 0

        else:
            # 知识库不存在或其他错误
            error_code = result.get("code")
            error_message = result.get("message", "未知错误")
            validation_result["error"] = {
                "code": error_code,
                "message": error_message
            }

            # 根据错误码判断是否为"不存在"错误
            if error_code == 100013:  # 文档中提到的"知识库不存在"错误码
                validation_result["error_type"] = "not_found"
            else:
                validation_result["error_type"] = "other_error"

        return validation_result

    except requests.exceptions.Timeout:
        return {
            "kb_id": kb_id,
            "exists": False,
            "valid": False,
            "error": {
                "code": "TIMEOUT",
                "message": "请求超时，可能网络问题或服务不可用"
            },
            "error_type": "timeout",
            "details": {}
        }

    except requests.exceptions.HTTPError as e:
        # 处理HTTP错误（非200状态码）
        try:
            error_result = e.response.json()
            error_code = error_result.get("code", "UNKNOWN_HTTP_ERROR")
            error_message = error_result.get("message", f"HTTP错误: {e.response.status_code}")
        except:
            error_code = "HTTP_ERROR"
            error_message = f"HTTP错误: {e.response.status_code}"

        return {
            "kb_id": kb_id,
            "exists": False,
            "valid": False,
            "error": {
                "code": error_code,
                "message": error_message
            },
            "error_type": "http_error",
            "details": {}
        }

    except requests.exceptions.RequestException as e:
        # 处理其他网络请求错误
        return {
            "kb_id": kb_id,
            "exists": False,
            "valid": False,
            "error": {
                "code": "REQUEST_ERROR",
                "message": f"请求失败: {str(e)}"
            },
            "error_type": "request_error",
            "details": {}
        }

    except Exception as e:
        # 处理其他意外错误
        return {
            "kb_id": kb_id,
            "exists": False,
            "valid": False,
            "error": {
                "code": "UNEXPECTED_ERROR",
                "message": f"未知错误: {str(e)}"
            },
            "error_type": "unexpected_error",
            "details": {}
        }

def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI知识库ID验证工具")
    print("=" * 60)

    # 读取环境变量
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：未设置 ZHIPU_KB_ID 环境变量")
        print("请执行：export ZHIPU_KB_ID=your_knowledge_base_id")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        print("请执行：export ZHIPUAI_API_KEY=your_api_key")
        sys.exit(1)

    print(f"🔍 验证知识库ID: {kb_id}")
    print()

    # 执行验证
    result = validate_knowledge_base(kb_id, api_key)

    # 输出验证结果
    print("验证结果：")
    print("-" * 40)

    if result["exists"] and result["valid"]:
        print("✅ 知识库验证成功")
        print(f"   知识库名称: {result['details'].get('name', '未知')}")
        print(f"   文档数量: {result['details'].get('document_size', 0)}")
        print(f"   总字数: {result['details'].get('word_num', 0)}")
        print(f"   向量化模型ID: {result['details'].get('embedding_id')}")
        print()
        print("🎉 该知识库存在且可用，可以安全上线！")

    elif result["exists"] and not result["valid"]:
        print("⚠️  知识库存在但没有文档")
        print(f"   知识库名称: {result['details'].get('name', '未知')}")
        print(f"   文档数量: {result['details'].get('document_size', 0)}")
        print()
        print("❌ 验证失败：知识库没有文档内容，无法使用")
        print("请先向知识库上传文档后再上线")

    else:
        print("❌ 知识库验证失败")

        if result.get("error"):
            error = result["error"]
            print(f"   错误码: {error['code']}")
            print(f"   错误信息: {error['message']}")

            # 根据错误类型给出建议
            error_type = result.get("error_type")
            if error_type == "not_found":
                print()
                print("💡 建议：请检查知识库ID是否正确")
            elif error_type == "timeout":
                print()
                print("💡 建议：请检查网络连接或服务状态")
            elif error_type == "http_error":
                print()
                print("💡 建议：请检查API Key是否有效")
            else:
                print()
                print("💡 建议：请检查API Key和知识库ID")

        print()
        print("❌ 验证失败：该知识库不存在或不可用，不能上线")

    print("=" * 60)

    # 返回适当的退出码
    if result["exists"] and result["valid"]:
        print("📋 退出码: 0 (验证通过)")
        sys.exit(0)
    else:
        print("📋 退出码: 1 (验证失败)")
        sys.exit(1)

if __name__ == "__main__":
    main()