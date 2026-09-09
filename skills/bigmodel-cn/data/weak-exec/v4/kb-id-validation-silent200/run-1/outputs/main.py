#!/usr/bin/env python3
"""
智谱托管知识库ID验证脚本

用途：验证环境变量 ZHIPU_KB_ID 中配置的知识库ID是否存在且可用
适用于发布流水线，宁可误报无效，也不能放坏ID上线

特性：
1. 严格验证：检查知识库是否存在，而不是只看HTTP状态码
2. 安全优先：宁可误报无效，也不放过坏ID
3. 明确输出：打印清晰的验证结论

API Key 从环境变量 ZHIPUAI_API_KEY 读取
"""
import os
import sys
import requests


def validate_knowledge_base(kb_id: str, api_key: str) -> dict:
    """
    验证知识库是否存在

    Args:
        kb_id: 知识库ID
        api_key: 智谱API Key

    Returns:
        dict: 包含验证结果的字典
    """
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建验证知识库详情的URL
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    print(f"正在验证知识库ID: {kb_id}")
    print(f"请求URL: {url}")

    try:
        # 发送GET请求
        response = requests.get(url, headers=headers, timeout=30)

        # 记录HTTP状态码（但仅作参考，不作为判断依据）
        http_status = response.status_code
        print(f"HTTP状态码: {http_status}")

        # 解析响应体
        try:
            response_data = response.json()
        except ValueError:
            return {
                "valid": False,
                "error": "响应不是有效的JSON格式",
                "http_status": http_status,
                "details": response.text
            }

        # 根据文档知识，知识库API的错误信息在code字段中
        # HTTP 200不表示成功，需要检查code是否为200
        response_code = response_data.get("code")

        print(f"响应code: {response_code}")
        print(f"完整响应: {response_data}")

        # 检查知识库是否存在
        if response_code == 200:
            # 获取知识库详情
            kb_info = response_data.get("data", {})
            kb_name = kb_info.get("name", "未知名称")

            return {
                "valid": True,
                "kb_name": kb_name,
                "kb_info": kb_info,
                "http_status": http_status,
                "response_code": response_code
            }
        else:
            # 知识库不存在或其他错误
            error_msg = response_data.get("message", "未知错误")

            # 常见错误码
            if response_code == 100013:
                error_msg = "知识库不存在"

            return {
                "valid": False,
                "error": error_msg,
                "error_code": response_code,
                "http_status": http_status,
                "details": response_data
            }

    except requests.exceptions.Timeout:
        return {
            "valid": False,
            "error": "请求超时",
            "http_status": None
        }
    except requests.exceptions.ConnectionError:
        return {
            "valid": False,
            "error": "连接失败",
            "http_status": None
        }
    except requests.exceptions.RequestException as e:
        return {
            "valid": False,
            "error": f"请求异常: {str(e)}",
            "http_status": None
        }


def main():
    """主函数"""
    print("=" * 60)
    print("智谱托管知识库ID验证工具")
    print("=" * 60)

    # 读取环境变量
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("❌ 错误: 未设置环境变量 ZHIPU_KB_ID")
        print("请确保设置了正确的知识库ID")
        sys.exit(1)

    if not api_key:
        print("❌ 错误: 未设置环境变量 ZHIPUAI_API_KEY")
        print("请确保设置了正确的API Key")
        sys.exit(1)

    print(f"配置信息:")
    print(f"  知识库ID: {kb_id}")
    print(f"  API Key: {'*' * (len(api_key) - 4)}{api_key[-4:] if len(api_key) >= 4 else '*' * len(api_key)}")
    print()

    # 执行验证
    result = validate_knowledge_base(kb_id, api_key)

    # 输出验证结果
    print("\n" + "=" * 60)
    print("验证结果:")

    if result["valid"]:
        kb_name = result["kb_name"]
        print(f"✅ 知识库验证通过")
        print(f"   知识库名称: {kb_name}")
        print(f"   知识库ID: {kb_id}")
        print(f"   文档数量: {result['kb_info'].get('document_size', 0)}")
        print(f"   总字数: {result['kb_info'].get('word_num', 0)}")
        print("\n🎉 该知识库可以安全上线使用")

        # 在CI环境中输出特定的退出码
        if os.environ.get("CI"):
            print("::notice::知识库验证通过，可以继续部署")

        sys.exit(0)
    else:
        error = result.get("error", "未知错误")
        error_code = result.get("error_code")
        http_status = result.get("http_status")

        print(f"❌ 知识库验证失败")
        print(f"   错误信息: {error}")

        if error_code:
            print(f"   错误码: {error_code}")

        if http_status:
            print(f"   HTTP状态码: {http_status}")

        print(f"\n⚠️  该知识库ID {kb_id} 无效，建议:")
        print("   1. 检查知识库ID是否正确")
        print("   2. 确认API Key有足够权限")
        print("   3. 联系管理员确认知识库状态")
        print("   4. 修正配置后重新验证")

        # 在CI环境中输出特定的错误信息
        if os.environ.get("CI"):
            print(f"::error title=知识库验证失败::错误: {error} (代码: {error_code})")

        sys.exit(1)


if __name__ == "__main__":
    main()