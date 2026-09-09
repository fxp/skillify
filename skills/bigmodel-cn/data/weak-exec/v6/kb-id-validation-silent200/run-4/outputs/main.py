#!/usr/bin/env python3
"""
智谱AI托管知识库ID验证脚本

功能：
- 验证配置中的知识库ID是否存在且可用
- 从环境变量读取配置：
  - ZHIPU_KB_ID: 知识库ID
  - ZHIPUAI_API_KEY: API Key
- 验证结果作为发布流水线卡点，宁可误报无效，不能放坏ID上线

输出：
- 明确打印校验结论
"""

import os
import sys
import requests
import json

def validate_knowledge_base():
    """验证知识库是否存在且可用"""

    # 从环境变量读取配置
    kb_id = os.getenv('ZHIPU_KB_ID')
    api_key = os.getenv('ZHIPUAI_API_KEY')

    # 检查环境变量
    if not kb_id:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        return False

    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False

    print(f"🔍 开始验证知识库 ID: {kb_id}")
    print(f"🔍 API Key 前缀: {api_key[:10]}...")

    # 构造请求头
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # 知识库详情接口
    url = f"https://open.bigmodel.cn/api/llm-application/open/knowledge/{kb_id}"

    try:
        # 发送请求
        response = requests.get(url, headers=headers, timeout=10)

        # 解析响应
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            print(f"❌ 错误：响应不是有效的JSON格式")
            print(f"HTTP状态码: {response.status_code}")
            print(f"响应内容: {response.text[:200]}...")
            return False

        # 知识库API的特殊处理：HTTP状态码可能是200，但业务码在body里
        if response.status_code != 200:
            print(f"❌ 错误：HTTP请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response_data}")
            return False

        # 检查业务错误码
        if 'code' in response_data:
            if response_data['code'] == 200:
                # 成功响应
                if 'data' in response_data and 'id' in response_data['data']:
                    kb_info = response_data['data']
                    print(f"✅ 知识库验证成功!")
                    print(f"   📚 知识库名称: {kb_info.get('name', 'N/A')}")
                    print(f"   📊 文档数量: {kb_info.get('document_size', 'N/A')}")
                    print(f"   💾 总字数: {kb_info.get('word_num', 'N/A')}")
                    return True
                else:
                    print("❌ 错误：响应格式异常，缺少data.id字段")
                    return False
            elif response_data['code'] == 100013:
                # 知识库不存在
                print("❌ 知识库验证失败: 知识库不存在")
                return False
            else:
                # 其他错误码
                print(f"❌ 知识库验证失败: 错误码 {response_data['code']}")
                print(f"   错误信息: {response_data.get('message', 'N/A')}")
                return False
        else:
            print("❌ 错误：响应中未找到code字段")
            return False

    except requests.exceptions.Timeout:
        print("❌ 错误：请求超时")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 错误：网络连接失败")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 错误：请求异常 - {str(e)}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("智谱AI托管知识库ID验证")
    print("=" * 60)

    # 执行验证
    is_valid = validate_knowledge_base()

    print("\n" + "=" * 60)

    # 输出最终结论
    if is_valid:
        print("🎉 校验结论: 知识库有效，可以上线")
        print("🟢 发布流水线可以通过")
        sys.exit(0)
    else:
        print("🚨 校验结论: 知识库无效，禁止上线")
        print("🔴 发布流水线被阻断")
        sys.exit(1)

if __name__ == "__main__":
    main()