#!/usr/bin/env python3
"""
知识库ID校验脚本
用途：验证配置中的智谱托管知识库ID是否存在且可用
特点：
- 从环境变量读取配置（ZHIPU_KB_ID 和 ZHIPUAI_API_KEY）
- 宁可误报无效，绝不放行坏ID
- 明确打印校验结论
"""

import os
import sys
import requests

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"

def validate_knowledge_base(kb_id: str, api_key: str) -> tuple[bool, str]:
    """
    校验知识库是否存在且可用

    Args:
        kb_id: 知识库ID
        api_key: 智谱AI API Key

    Returns:
        (is_valid: bool, message: str)
    """
    if not kb_id:
        return False, "错误：知识库ID为空"

    if not api_key:
        return False, "错误：API Key为空"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 调用知识库详情接口
        url = f"{BASE_URL}/llm-application/open/knowledge/{kb_id}"
        print(f"正在查询知识库详情：{url}")

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查HTTP状态码

        # 解析响应
        result = response.json()

        # 重要：知识库API的HTTP状态码200不代表成功，需要检查响应中的code字段
        if result.get("code") == 200:
            # 知识库存在，获取基本信息
            data = result.get("data", {})
            kb_name = data.get("name", "未命名知识库")
            embedding_id = data.get("embedding_id", "未知")
            doc_size = data.get("document_size", 0)

            return True, f"✅ 知识库有效 | ID: {kb_id} | 名称: {kb_name} | 文档数: {doc_size} | 向量化模型ID: {embedding_id}"
        else:
            # 知识库不存在或返回其他错误
            error_code = result.get("code", "未知")
            error_msg = result.get("message", "未知错误")

            if error_code == 100013 and "知识库不存在" in error_msg:
                return False, f"❌ 知识库不存在 | ID: {kb_id} | 错误码: {error_code}"
            else:
                # 其他错误，为了安全起见，也认为是无效的
                return False, f"❌ 知识库不可用 | ID: {kb_id} | 错误码: {error_code} | 错误信息: {error_msg}"

    except requests.exceptions.Timeout:
        return False, f"❌ 请求超时 | ID: {kb_id}"
    except requests.exceptions.ConnectionError:
        return False, f"❌ 连接失败 | 请检查网络或API地址 | ID: {kb_id}"
    except requests.exceptions.HTTPError as e:
        # HTTP错误（如401认证失败）
        return False, f"❌ HTTP错误 | {str(e)} | ID: {kb_id}"
    except Exception as e:
        # 其他异常（如JSON解析错误）
        return False, f"❌ 系统异常 | {str(e)} | ID: {kb_id}"

def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI托管知识库ID校验工具")
    print("=" * 60)

    # 从环境变量读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    # 显示配置信息（部分脱敏）
    masked_key = "***" + (api_key[-4:] if len(api_key) > 4 else "***") if api_key else "未设置"

    print("\n配置信息：")
    print(f"  知识库ID: {kb_id if kb_id else '未设置'}")
    print(f"  API Key: {masked_key}")
    print()

    if not kb_id:
        print("❌ 错误：请设置环境变量 ZHIPU_KB_ID")
        sys.exit(1)

    if not api_key:
        print("❌ 错误：请设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    # 执行校验
    is_valid, message = validate_knowledge_base(kb_id, api_key)

    # 打印结果
    print("\n" + "=" * 60)
    print("校验结果：")
    print(message)
    print("=" * 60)

    # 返回状态码
    if is_valid:
        print("\n🎉 知识库验证通过，可以上线使用")
        sys.exit(0)
    else:
        print("\n⚠️  知识库验证失败，请检查配置或联系管理员")
        sys.exit(1)

if __name__ == "__main__":
    main()