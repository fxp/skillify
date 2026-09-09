#!/usr/bin/env python3
"""
智谱托管知识库 ID 校验脚本

用途：验证配置中的知识库 ID 是否有效，用于发布流水线卡点。
严格校验 - 宁可误报无效，也不能放坏 ID 上线。

环境变量：
- ZHIPU_KB_ID: 要验证的知识库 ID
- ZHIPUAI_API_KEY: 智谱 AI API Key
"""

import os
import requests
import sys
from typing import Dict, Any, Optional


def validate_knowledge_base(kb_id: str, api_key: str) -> Dict[str, Any]:
    """
    验证知识库 ID 是否有效

    Args:
        kb_id: 知识库 ID
        api_key: 智谱 AI API Key

    Returns:
        包含校验结果的字典
    """
    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 知识库详情接口
    url = "https://open.bigmodel.cn/api/llm-application/open/knowledge/{id}".format(id=kb_id)

    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=10)

        # 响应数据
        response_data = response.json()

        # 记录原始响应用于调试
        result = {
            "kb_id": kb_id,
            "http_status": response.status_code,
            "response_code": response_data.get("code"),
            "message": response_data.get("message"),
            "valid": False,
            "debug_info": {
                "has_data": "data" in response_data,
                "data_keys": list(response_data.get("data", {}).keys()) if "data" in response_data else []
            }
        }

        # 判断结果
        # 根据文档：知识库不存在时返回 code=100013，存在时返回 code=200
        if response_data.get("code") == 200:
            result["valid"] = True
            result["reason"] = "知识库存在且可访问"
            if "data" in response_data:
                result["name"] = response_data["data"].get("name")
                result["embedding_id"] = response_data["data"].get("embedding_id")
                result["document_size"] = response_data["data"].get("document_size")
        elif response_data.get("code") == 100013:
            result["valid"] = False
            result["reason"] = "知识库不存在"
        else:
            # 其他错误码，保守起见认为无效
            result["valid"] = False
            result["reason"] = f"返回未知错误码: {response_data.get('code')}, 消息: {response_data.get('message')}"

        return result

    except requests.exceptions.Timeout:
        return {
            "kb_id": kb_id,
            "valid": False,
            "reason": "请求超时",
            "error": "连接超时，请检查网络或API Key是否有效"
        }
    except requests.exceptions.ConnectionError:
        return {
            "kb_id": kb_id,
            "valid": False,
            "reason": "连接失败",
            "error": "无法连接到智谱API服务器"
        }
    except Exception as e:
        return {
            "kb_id": kb_id,
            "valid": False,
            "reason": "请求异常",
            "error": str(e)
        }


def main():
    """主函数"""
    print("=" * 60)
    print("智谱托管知识库 ID 校验")
    print("=" * 60)

    # 从环境变量读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：环境变量 ZHIPU_KB_ID 未设置")
        print("请设置要验证的知识库 ID")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：环境变量 ZHIPUAI_API_KEY 未设置")
        print("请设置智谱 AI API Key")
        sys.exit(1)

    # 打印基本信息（脱敏处理）
    masked_kb_id = kb_id[:8] + "*" * (len(kb_id) - 8) if len(kb_id) > 8 else "*" * len(kb_id)
    print(f"📋 待校验知识库 ID: {masked_kb_id}")
    print(f"🔑 API Key: {'*' * 8 + api_key[-8:]}")
    print()

    # 执行校验
    print("🔄 正在验证知识库...")
    result = validate_knowledge_base(kb_id, api_key)

    # 打印结果
    print("\n" + "=" * 60)
    print("校验结果")
    print("=" * 60)

    if result["valid"]:
        print("✅ 知识库校验通过")
        print(f"   知识库ID: {result['kb_id']}")
        print(f"   状态: {result['reason']}")
        if "name" in result:
            print(f"   知识库名称: {result['name']}")
        if "document_size" in result:
            print(f"   文档数量: {result['document_size']}")
        print("\n🎉 该知识库可以正常使用，可以上线！")
    else:
        print("❌ 知识库校验失败")
        print(f"   知识库ID: {result['kb_id']}")
        print(f"   失败原因: {result['reason']}")
        if "error" in result:
            print(f"   错误详情: {result['error']}")
        if "http_status" in result:
            print(f"   HTTP状态码: {result['http_status']}")
        print("\n⚠️  该知识库不可用，不能上线！")

    # 退出代码：0=成功，1=失败
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()