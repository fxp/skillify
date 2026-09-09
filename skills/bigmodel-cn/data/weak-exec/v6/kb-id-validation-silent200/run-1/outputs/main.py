#!/usr/bin/env python3
"""
智谱托管知识库 ID 验证脚本

用途：验证配置中的知识库 ID 是否存在且可用
配置：
- ZHIPU_KB_ID: 知识库 ID
- ZHIPUAI_API_KEY: 智谱 API Key

要求：宁可误报无效，也不能放坏 ID 上线
"""

import os
import sys
import requests

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
HEADERS = {"Authorization": f"Bearer {os.environ.get('ZHIPUAI_API_KEY')}"}


def check_knowledge_base_exists(kb_id):
    """
    验证知识库是否存在

    Args:
        kb_id (str): 知识库 ID

    Returns:
        tuple: (是否有效, 错误信息, 详细信息)
    """
    if not kb_id:
        return False, "知识库 ID 为空", None

    # 构造请求 URL
    url = f"{BASE_URL}/llm-application/open/knowledge/{kb_id}"

    try:
        # 发送请求
        resp = requests.get(url, headers=HEADERS, timeout=10)

        # 重要：知识库 API 返回 HTTP 200，但结果在响应体的 code 字段里
        # 不能使用 resp.raise_for_status()
        result = resp.json()

        # 检查响应状态
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {resp.text}", None

        # 检查业务状态码
        if "code" not in result:
            return False, "响应格式错误：缺少 code 字段", result

        if result["code"] == 200:
            # 知识库存在，获取详细信息
            kb_info = {
                "id": result.get("data", {}).get("id"),
                "name": result.get("data", {}).get("name"),
                "document_size": result.get("data", {}).get("document_size"),
                "length": result.get("data", {}).get("length"),
                "word_num": result.get("data", {}).get("word_num"),
            }
            return True, "知识库有效", kb_info
        elif result["code"] == 100013:
            return False, "知识库不存在", result
        else:
            error_msg = result.get("message", f"未知错误码: {result['code']}")
            return False, f"知识库错误: {error_msg}", result

    except requests.exceptions.RequestException as e:
        return False, f"网络请求失败: {str(e)}", None
    except Exception as e:
        return False, f"解析响应失败: {str(e)}", None


def main():
    """主函数"""
    # 读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID", "").strip()

    if not kb_id:
        print("❌ 配置错误：ZHIPU_KB_ID 环境变量未设置或为空")
        sys.exit(1)

    print(f"🔍 开始验证知识库 ID: {kb_id}")
    print("-" * 50)

    # 验证知识库
    is_valid, error_msg, detail = check_knowledge_base_exists(kb_id)

    # 打印结果
    if is_valid:
        print("✅ 验证通过：知识库有效")
        if detail:
            print("\n📋 知识库详情:")
            print(f"   ID: {detail['id']}")
            print(f"   名称: {detail['name']}")
            print(f"   文档数量: {detail['document_size']}")
            print(f"   总长度: {detail['length']} 字符")
            print(f"   总字数: {detail['word_num']} 字")
    else:
        print("❌ 验证失败：知识库无效")
        print(f"   错误原因: {error_msg}")
        if detail:
            print(f"   详细信息: {detail}")

    print("-" * 50)

    # 输出明确的结论（用于 CI/CD 集成）
    if is_valid:
        print("\n🎯 验证结论: VALID - 知识库可用")
        sys.exit(0)
    else:
        print("\n🎯 验证结论: INVALID - 知识库不可用")
        sys.exit(1)


if __name__ == "__main__":
    main()