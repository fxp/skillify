#!/usr/bin/env python3
"""
智谱AI托管知识库ID校验脚本
用途：验证配置中的知识库ID是否存在且可用，作为发布流水线的卡点检查
要求：宁可误报无效，也不能放坏ID上线
"""

import os
import sys
import requests
import json

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
KB_ID = os.environ.get("ZHIPU_KB_ID")

def print_verification_result(is_valid, message, details=None):
    """打印校验结果"""
    print("=" * 60)
    print("🔍 知识库ID校验结果")
    print("=" * 60)
    print(f"📋 校验的知识库ID: {KB_ID}")
    print(f"✅ 校验状态: {'通过' if is_valid else '不通过'}")
    print(f"📝 校验详情: {message}")

    if details:
        print("\n📊 详细信息:")
        print(json.dumps(details, indent=2, ensure_ascii=False))

    print("=" * 60)

    if is_valid:
        print("\n🎉 知识库ID验证通过，可以发布上线")
        sys.exit(0)
    else:
        print("\n❌ 知识库ID验证失败，阻止发布上线")
        sys.exit(1)

def verify_knowledge_base():
    """验证知识库是否存在且可用"""
    # 检查环境变量
    if not API_KEY:
        print_verification_result(
            False,
            "API Key未配置，请设置环境变量 ZHIPUAI_API_KEY",
            {"error": "Missing ZHIPUAI_API_KEY environment variable"}
        )

    if not KB_ID:
        print_verification_result(
            False,
            "知识库ID未配置，请设置环境变量 ZHIPU_KB_ID",
            {"error": "Missing ZHIPU_KB_ID environment variable"}
        )

    # 构造请求URL
    url = f"{BASE_URL}/llm-application/open/knowledge/{KB_ID}"

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    print(f"🚀 开始验证知识库ID: {KB_ID}")
    print(f"🔗 请求地址: {url}")

    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=30)

        # 记录原始响应（用于调试）
        raw_response = response.text

        # 解析响应
        try:
            resp_data = response.json()
        except json.JSONDecodeError:
            print_verification_result(
                False,
                "服务器响应不是有效的JSON格式",
                {"error": "Invalid JSON response", "raw_response": raw_response[:500] + "..."}
            )

        # 根据技能文档，知识库API的HTTP状态码可能是200，但真实状态在code字段中
        # code=200 表示成功
        # code=100013 表示知识库不存在
        # 其他code表示各种错误

        if response.status_code != 200:
            # HTTP状态码不是200，直接报错
            print_verification_result(
                False,
                f"HTTP请求失败，状态码: {response.status_code}",
                {
                    "status_code": response.status_code,
                    "response": resp_data,
                    "note": "根据技能文档，知识库API可能返回200状态码但实际失败，请检查response.code字段"
                }
            )

        # 检查响应中的code字段
        if "code" not in resp_data:
            print_verification_result(
                False,
                "响应中缺少code字段",
                {
                    "response": resp_data,
                    "note": "响应格式不符合预期，可能API已变更"
                }
            )

        resp_code = resp_data["code"]

        if resp_code == 200:
            # 知识库存在且正常
            kb_info = resp_data.get("data", {})
            kb_name = kb_info.get("name", "未知名称")
            doc_count = kb_info.get("document_size", 0)
            total_length = kb_info.get("length", 0)
            word_num = kb_info.get("word_num", 0)

            print_verification_result(
                True,
                f"知识库存在且正常，名称: {kb_name}",
                {
                    "knowledge_base_id": KB_ID,
                    "name": kb_name,
                    "document_count": doc_count,
                    "total_length": total_length,
                    "word_num": word_num,
                    "embedding_id": kb_info.get("embedding_id"),
                    "contextual": kb_info.get("contextual"),
                    "message": resp_data.get("message", "success")
                }
            )

        elif resp_code == 100013:
            # 知识库不存在
            print_verification_result(
                False,
                "知识库不存在",
                {
                    "error_code": resp_code,
                    "error_message": resp_data.get("message", "知识库不存在"),
                    "note": "请检查知识库ID是否正确，或该知识库已被删除"
                }
            )

        else:
            # 其他错误
            error_msg = resp_data.get("message", f"未知错误 (code: {resp_code})")
            print_verification_result(
                False,
                f"知识库验证失败: {error_msg}",
                {
                    "error_code": resp_code,
                    "error_message": error_msg,
                    "full_response": resp_data
                }
            )

    except requests.exceptions.Timeout:
        print_verification_result(
            False,
            "请求超时，无法验证知识库",
            {"error": "Request timeout", "timeout": 30}
        )

    except requests.exceptions.ConnectionError:
        print_verification_result(
            False,
            "无法连接到智谱AI服务器",
            {"error": "Connection error", "url": url}
        )

    except requests.exceptions.RequestException as e:
        print_verification_result(
            False,
            f"请求发生异常: {str(e)}",
            {"error": str(e), "type": type(e).__name__}
        )

    except Exception as e:
        print_verification_result(
            False,
            f"验证过程中发生未知错误: {str(e)}",
            {"error": str(e), "type": type(e).__name__}
        )

def main():
    """主函数"""
    print("🔐 智谱AI托管知识库ID校验工具")
    print("此脚本将验证配置中的知识库ID是否存在且可用")
    print()

    verify_knowledge_base()

if __name__ == "__main__":
    main()