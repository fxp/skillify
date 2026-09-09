#!/usr/bin/env python3
"""
智谱托管知识库ID校验脚本
用途：验证配置的知识库ID是否存在且可用，作为发布流水线的卡点检查
环境变量：
- ZHIPU_KB_ID: 要验证的知识库ID
- ZHIPUAI_API_KEY: 智谱API Key
"""

import os
import requests
import sys
from typing import Dict, Any, Tuple

def validate_zhipu_knowledge_base() -> Tuple[bool, str, Dict[str, Any]]:
    """
    验证智谱知识库ID是否存在且可用

    Returns:
        Tuple[bool, str, Dict]:
        - bool: 是否验证通过（True=有效，False=无效）
        - str: 验证结果消息
        - Dict: 完整的API响应（用于调试）
    """
    # 从环境变量读取配置
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    # 检查环境变量
    if not kb_id:
        return False, "错误：未设置 ZHIPU_KB_ID 环境变量", {}

    if not api_key:
        return False, "错误：未设置 ZHIPUAI_API_KEY 环境变量", {}

    # 构建请求URL
    base_url = "https://open.bigmodel.cn/api"
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    # 设置请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发起请求
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # 检查HTTP错误状态码

        # 解析响应
        response_data = response.json()

        # 根据文档说明：HTTP状态码永远是200，真实结果在response["code"]中
        if response.get("code") == 200:
            # 知识库存在且正常
            kb_info = response.get("data", {})
            kb_name = kb_info.get("name", "未知名称")
            doc_count = kb_info.get("document_size", 0)
            total_length = kb_info.get("length", 0)

            message = (
                f"✅ 知识库校验通过\n"
                f"   - 知识库ID: {kb_id}\n"
                f"   - 知识库名称: {kb_name}\n"
                f"   - 文档数量: {doc_count}\n"
                f"   - 总长度: {total_length:,} 字符"
            )
            return True, message, response_data
        else:
            # 知识库不存在或其他错误
            error_code = response.get("code", "未知错误码")
            error_msg = response.get("message", "未知错误")

            message = (
                f"❌ 知识库校验失败\n"
                f"   - 知识库ID: {kb_id}\n"
                f"   - 错误码: {error_code}\n"
                f"   - 错误信息: {error_msg}"
            )
            return False, message, response_data

    except requests.exceptions.HTTPError as http_err:
        # HTTP请求失败（网络错误、401等）
        status_code = http_err.response.status_code
        if status_code == 401:
            message = f"❌ API认证失败，请检查 ZHIPUAI_API_KEY 是否正确"
        else:
            message = f"❌ HTTP请求失败: {status_code} - {str(http_err)}"
        return False, message, {}

    except requests.exceptions.RequestException as req_err:
        # 其他网络错误（超时、连接失败等）
        message = f"❌ 网络请求异常: {str(req_err)}"
        return False, message, {}

    except Exception as e:
        # 其他未知错误
        message = f"❌ 未知错误: {str(e)}"
        return False, message, {}

def main():
    """主函数"""
    print("=" * 60)
    print("智谱托管知识库ID校验")
    print("=" * 60)

    # 验证知识库
    is_valid, message, response_data = validate_zhipu_knowledge_base()

    # 打印结果
    print("\n" + message)
    print("\n" + "=" * 60)

    # 输出调试信息（可选）
    if os.environ.get('DEBUG', '').lower() == 'true':
        print("\n[调试信息] 完整API响应:")
        print("-" * 40)
        try:
            import json
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
        except:
            print(str(response_data))
        print("-" * 40)

    # 根据验证结果设置退出码
    # 0: 成功，知识库有效
    # 1: 失败，知识库无效
    # 2: 配置错误，环境变量缺失
    if is_valid:
        print("\n🎉 知识库验证通过，可以上线！")
        sys.exit(0)
    else:
        print("\n🚨 知识库验证失败，阻止上线！")
        if os.environ.get('ZHIPU_KB_ID'):
            sys.exit(1)
        else:
            sys.exit(2)

if __name__ == "__main__":
    main()