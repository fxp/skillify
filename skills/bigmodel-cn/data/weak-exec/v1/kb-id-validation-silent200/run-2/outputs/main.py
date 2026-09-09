#!/usr/bin/env python3
"""
智谱托管知识库 ID 验证脚本

用途：验证配置中的知识库 ID 是否存在且可用
这个脚本会作为发布流水线的卡点，必须确保验证的准确性
宁可误报无效，也不能放一个坏 ID 上线

使用方法：
1. 设置环境变量 ZHIPUAI_API_KEY（智谱 API Key）
2. 设置环境变量 ZHIPU_KB_ID（要验证的知识库 ID）
3. 运行：python3 main.py
"""

import os
import sys
import requests
import json

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
VERIFY_ENDPOINT = f"{BASE_URL}/llm-application/open/knowledge/{{kb_id}}"

def load_env_vars():
    """加载必需的环境变量"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    kb_id = os.environ.get('ZHIPU_KB_ID')

    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        print("请设置智谱 AI 的 API Key")
        sys.exit(1)

    if not kb_id:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        print("请设置要验证的知识库 ID")
        sys.exit(1)

    return api_key, kb_id

def validate_knowledge_base(api_key, kb_id):
    """
    验证知识库是否存在且可用

    Args:
        api_key: 智谱 AI API Key
        kb_id: 知识库 ID

    Returns:
        tuple: (is_valid, error_code, error_message, response_data)
    """
    # 构造请求 URL
    url = VERIFY_ENDPOINT.format(kb_id=kb_id)

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发起请求
        print(f"🔍 正在验证知识库 ID: {kb_id}")
        print(f"📡 请求地址: {url}")

        response = requests.get(url, headers=headers, timeout=30)

        # 注意：根据文档，知识库 API 即使出错也可能返回 HTTP 200
        # 实际错误信息在响应体的 code 字段中
        response_data = response.json()

        print(f"📊 响应状态码: {response.status_code}")
        print(f"📦 响应数据: {json.dumps(response_data, indent=2, ensure_ascii=False)}")

        # 检查业务错误码
        if response_data.get("code") == 200:
            # 知识库存在且可用
            return True, None, None, response_data
        else:
            # 知识库不存在或有其他问题
            error_code = response_data.get("code")
            error_message = response_data.get("message", "未知错误")
            return False, error_code, error_message, response_data

    except requests.exceptions.Timeout:
        print(f"❌ 错误：请求超时（30秒）")
        return False, "timeout", "请求超时", None
    except requests.exceptions.ConnectionError:
        print(f"❌ 错误：连接失败，无法访问智谱 API 服务器")
        return False, "connection_error", "连接失败", None
    except requests.exceptions.RequestException as e:
        print(f"❌ 错误：请求异常 - {str(e)}")
        return False, "request_error", str(e), None
    except json.JSONDecodeError:
        print(f"❌ 错误：响应解析失败，返回的不是有效的 JSON")
        return False, "parse_error", "响应解析失败", None
    except Exception as e:
        print(f"❌ 错误：未预期的异常 - {str(e)}")
        return False, "unexpected_error", str(e), None

def main():
    """主函数"""
    print("=" * 60)
    print("智谱托管知识库 ID 验证工具")
    print("=" * 60)

    # 加载环境变量
    api_key, kb_id = load_env_vars()

    print(f"\n🔑 API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"📚 知识库 ID: {kb_id}")
    print()

    # 验证知识库
    is_valid, error_code, error_message, response_data = validate_knowledge_base(api_key, kb_id)

    # 输出验证结论
    print("\n" + "=" * 60)
    print("📋 验证结论")
    print("=" * 60)

    if is_valid:
        print("✅ 验证通过")
        print("   • 知识库存在")
        print("   • 知识库可用")
        print("   • 可以安全上线")

        # 显示知识库基本信息
        if response_data and "data" in response_data:
            data = response_data["data"]
            print("\n📊 知识库信息:")
            print(f"   • 名称: {data.get('name', '未知')}")
            print(f"   • 向量化模型: {data.get('embedding_model', '未知')}")
            print(f"   • 文档数量: {data.get('document_size', 0)}")
            print(f"   • 总长度: {data.get('length', 0)} 字")
            print(f"   • 总字数: {data.get('word_num', 0)} 字")
            print(f"   • 上下文增强: {'是' if data.get('contextual') == 1 else '否'}")

        print("\n🎉 结论：知识库验证通过，可以上线")
        sys.exit(0)
    else:
        print("❌ 验证失败")

        if error_code:
            print(f"   • 错误码: {error_code}")
        if error_message:
            print(f"   • 错误信息: {error_message}")

        # 根据错误类型给出具体的建议
        print("\n💡 建议:")
        if error_code == "100013":
            print("   • 知识库不存在，请检查知识库 ID 是否正确")
            print("   • 请登录智谱控制台确认知识库 ID")
        elif error_code in ["1000", "1001", "1003"]:
            print("   • API Key 无效或已过期")
            print("   • 请检查 ZHIPUAI_API_KEY 环境变量")
        elif error_code == "timeout":
            print("   • 请求超时，可能是网络问题或服务繁忙")
            print("   • 请稍后重试")
        elif error_code == "connection_error":
            print("   • 无法连接到智谱 API 服务器")
            print("   • 请检查网络连接")
        elif error_code in ["1220", "1221", "1222"]:
            print("   • API 权限不足或 API 不存在")
            print("   • 请确认 API Key 有访问知识库的权限")
        else:
            print("   • 请检查配置是否正确")
            print("   • 联系技术支持")

        print("\n⚠️ 结论：知识库验证失败，不能上线")
        print("   • 请修复问题后重新验证")
        print("   • 绝不能放一个无效的知识库 ID 上线")

        sys.exit(1)

if __name__ == "__main__":
    main()