#!/usr/bin/env python3
"""
知识库ID校验脚本
用于验证智谱AI托管知识库ID是否存在且可用
"""

import os
import sys
import requests
import json

def validate_knowledge_base():
    """验证知识库是否存在且可用"""

    # 从环境变量读取配置
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    kb_id = os.environ.get('ZHIPU_KB_ID')

    # 检查环境变量是否设置
    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    if not kb_id:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        sys.exit(1)

    print(f"🔍 正在验证知识库 ID: {kb_id}")

    # 构造请求
    url = f"https://open.bigmodel.cn/api/llm-application/open/knowledge/{kb_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=30)

        # 解析响应
        response_data = response.json()

        # 检查 HTTP 状态码和业务错误码
        if response.status_code != 200:
            print(f"❌ 错误：HTTP 请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response_data}")
            return False

        # 根据业务错误码判断
        if response_data.get('code') == 200:
            # 知识库存在
            kb_info = response_data.get('data', {})
            print(f"✅ 知识库验证成功！")
            print(f"   知识库名称: {kb_info.get('name', '未知')}")
            print(f"   文档数量: {kb_info.get('document_size', 0)}")
            print(f"   总字数: {kb_info.get('word_num', 0)}")
            return True
        elif response_data.get('code') == 100013:
            # 知识库不存在
            print("❌ 知识库验证失败：知识库不存在")
            return False
        else:
            # 其他错误
            error_code = response_data.get('code')
            error_msg = response_data.get('message', '未知错误')
            print(f"❌ 知识库验证失败：错误码 {error_code} - {error_msg}")
            return False

    except requests.exceptions.Timeout:
        print("❌ 错误：请求超时")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 错误：网络请求异常 - {e}")
        return False
    except json.JSONDecodeError:
        print("❌ 错误：响应格式解析失败")
        return False
    except Exception as e:
        print(f"❌ 错误：未知异常 - {e}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("智谱AI知识库ID校验工具")
    print("=" * 50)

    # 验证知识库
    is_valid = validate_knowledge_base()

    # 输出结论
    print("\n" + "=" * 50)
    if is_valid:
        print("🎉 校验结论：知识库有效，可以上线使用")
        sys.exit(0)
    else:
        print("⚠️  校验结论：知识库无效，不能上线使用")
        sys.exit(1)

if __name__ == "__main__":
    main()