#!/usr/bin/env python3
"""
智谱托管知识库 ID 校验脚本
用于发布流水线验证知识库是否存在且可用
"""

import os
import requests
import sys


def validate_knowledge_base():
    """验证知识库是否存在且可用"""
    # 从环境变量读取配置
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：环境变量 ZHIPU_KB_ID 未设置")
        return False

    if not api_key:
        print("❌ 错误：环境变量 ZHIPUAI_API_KEY 未设置")
        return False

    print(f"🔍 正在验证知识库 ID: {kb_id}")

    # API 基础配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构造请求 URL
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    try:
        # 发送请求获取知识库详情
        print("📡 正在查询知识库详情...")
        response = requests.get(url, headers=headers)

        # 重要：知识库 API 的错误处理特殊机制
        # 即使 HTTP 状态码是 200，真实错误码在响应体的 code 字段中
        response_data = response.json()

        # 检查 HTTP 状态码
        if response.status_code != 200:
            print(f"❌ HTTP 状态码异常: {response.status_code}")
            return False

        # 检查响应体中的 code 字段（这是关键！）
        if 'code' not in response_data:
            print("❌ 响应格式错误：缺少 code 字段")
            return False

        if response_data['code'] != 200:
            error_msg = response_data.get('message', '未知错误')
            print(f"❌ 知识库验证失败: {error_msg}")
            return False

        # 知识库存在，检查详细信息
        if 'data' in response_data and response_data['data']:
            kb_data = response_data['data']
            name = kb_data.get('name', '未知名称')
            document_size = kb_data.get('document_size', 0)
            length = kb_data.get('length', 0)
            word_num = kb_data.get('word_num', 0)

            print(f"✅ 知识库验证成功！")
            print(f"   📚 名称: {name}")
            print(f"   📄 文档数量: {document_size}")
            print(f"   📝 总长度: {length}")
            print(f"   🔤 总字数: {word_num}")
            return True
        else:
            print("❌ 响应数据异常：data 字段为空")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 请求异常: {e}")
        return False
    except Exception as e:
        print(f"❌ 未知错误: {e}")
        return False


def main():
    """主函数"""
    print("=" * 50)
    print("智谱托管知识库 ID 校验")
    print("=" * 50)

    # 执行验证
    is_valid = validate_knowledge_base()

    # 输出最终结论
    print("\n" + "=" * 50)
    if is_valid:
        print("🎉 校验结论：知识库有效，可以通过发布流水线")
        print("=" * 50)
        sys.exit(0)
    else:
        print("💀 校验结论：知识库无效，阻止发布流水线")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()