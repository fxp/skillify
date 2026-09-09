#!/usr/bin/env python3
"""
智谱托管知识库 ID 验证脚本
用于验证配置中的知识库 ID 是否存在且可用
严格验证：宁可误报无效，也不能放一个坏 ID 上线
"""

import os
import sys
import requests

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
KB_ID = os.environ.get("ZHIPU_KB_ID")

def validate_knowledge_base():
    """验证知识库是否存在且可用"""

    # 检查环境变量
    if not API_KEY:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False

    if not KB_ID:
        print("❌ 错误：未设置环境变量 ZHIPU_KB_ID")
        return False

    print(f"🔍 正在验证知识库 ID: {KB_ID}")
    print(f"🔑 API Key: {API_KEY[:10]}...")  # 只显示前10位，保护隐私

    try:
        # 构造请求 URL
        url = f"{BASE_URL}/llm-application/open/knowledge/{KB_ID}"

        # 设置请求头
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        # 发送 GET 请求
        print("📡 发送请求到知识库详情接口...")
        response = requests.get(url, headers=headers, timeout=30)

        # 检查 HTTP 状态码
        if response.status_code != 200:
            print(f"❌ HTTP 请求失败，状态码: {response.status_code}")
            print(f"   响应内容: {response.text}")
            return False

        # 解析 JSON 响应
        try:
            resp_data = response.json()
        except ValueError as e:
            print(f"❌ 解析 JSON 响应失败: {e}")
            print(f"   响应内容: {response.text}")
            return False

        # 检查响应中的 code 字段
        if "code" not in resp_data:
            print("❌ 响应中缺少 code 字段")
            print(f"   响应内容: {resp_data}")
            return False

        # 根据文档，知识库不存在时 code=100013
        if resp_data["code"] == 200:
            # 知识库存在
            kb_info = resp_data.get("data", {})
            name = kb_info.get("name", "未知名称")
            document_size = kb_info.get("document_size", 0)
            length = kb_info.get("length", 0)

            print(f"✅ 知识库验证成功！")
            print(f"   📚 知识库名称: {name}")
            print(f"   📄 文档数量: {document_size}")
            print(f"   📝 内容长度: {length}")
            return True

        elif resp_data["code"] == 100013:
            # 知识库不存在
            print("❌ 知识库不存在")
            if "message" in resp_data:
                print(f"   错误信息: {resp_data['message']}")
            return False

        else:
            # 其他错误码
            print(f"❌ 知识库验证失败，错误码: {resp_data['code']}")
            if "message" in resp_data:
                print(f"   错误信息: {resp_data['message']}")
            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时（30秒）")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误，无法访问智谱 API")
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
    print("智谱托管知识库 ID 验证工具")
    print("=" * 50)

    # 验证知识库
    is_valid = validate_knowledge_base()

    print("\n" + "=" * 50)
    if is_valid:
        print("🎉 验证结论：知识库有效，可以通过上线检查")
        print("✅ [有效] 知识库存在且可用")
        sys.exit(0)
    else:
        print("🚨 验证结论：知识库无效，阻止上线")
        print("❌ [无效] 知识库不存在或不可用")
        sys.exit(1)

if __name__ == "__main__":
    main()