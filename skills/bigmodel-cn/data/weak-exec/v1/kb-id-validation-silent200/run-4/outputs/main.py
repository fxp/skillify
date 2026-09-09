#!/usr/bin/env python3
"""
智谱托管知识库 ID 校验脚本

用途：验证配置中的知识库 ID 是否有效、能否正常使用
验证结果将作为发布流水线的卡点，确保不会将无效的知识库 ID 上线

环境变量要求：
- ZHIPU_KB_ID: 待验证的知识库 ID
- ZHIPUAI_API_KEY: 智谱 AI API Key

输出：
- 明确打印校验结论（有效/无效）
- 退出码：0=有效，1=无效
"""

import os
import sys
import requests

def validate_knowledge_base():
    """验证知识库 ID 是否有效"""

    # 1. 读取环境变量
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    # 2. 检查环境变量是否设置
    if not kb_id:
        print("❌ 错误：环境变量 ZHIPU_KB_ID 未设置")
        return False

    if not api_key:
        print("❌ 错误：环境变量 ZHIPUAI_API_KEY 未设置")
        return False

    print(f"🔍 开始验证知识库 ID: {kb_id[:20]}..." if len(kb_id) > 20 else f"🔍 开始验证知识库 ID: {kb_id}")

    # 3. 构造请求
    base_url = "https://open.bigmodel.cn/api"
    url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 4. 发起请求
    try:
        print("📡 正在调用知识库详情接口...")
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 响应状态码: HTTP {response.status_code}")

        # 5. 解析响应
        try:
            resp_data = response.json()
        except ValueError as e:
            print(f"❌ 错误：响应不是有效的 JSON 格式 - {e}")
            print(f"响应内容: {response.text[:200]}...")
            return False

        # 6. 判断知识库是否存在
        # 根据文档，即使知识库不存在，HTTP 状态码也是 200
        # 真实的错误码在响应体的 code 字段里
        if response.status_code != 200:
            print(f"❌ 错误：接口返回异常状态码 {response.status_code}")
            print(f"响应内容: {resp_data}")
            return False

        # 检查响应中的 code 字段
        if 'code' not in resp_data:
            print("❌ 错误：响应中没有 code 字段")
            return False

        if resp_data['code'] != 200:
            # 知识库不存在的错误码是 10013
            if resp_data['code'] == 100013:
                print("❌ 结论：知识库不存在")
                print(f"   错误码: {resp_data['code']}")
                print(f"   错误信息: {resp_data.get('message', '未知错误')}")
            else:
                print("❌ 结论：知识库无效")
                print(f"   错误码: {resp_data['code']}")
                print(f"   错误信息: {resp_data.get('message', '未知错误')}")
            return False

        # 7. 检查响应数据是否完整
        if 'data' not in resp_data:
            print("❌ 错误：响应中没有 data 字段")
            return False

        data = resp_data['data']

        # 验证关键字段是否存在
        required_fields = ['id', 'name']
        for field in required_fields:
            if field not in data:
                print(f"❌ 错误：响应数据中缺少必需字段 '{field}'")
                return False

        # 8. 验证知识库 ID 是否匹配
        if data['id'] != kb_id:
            print("❌ 错误：响应中的知识库 ID 与请求的不一致")
            print(f"   请求的 ID: {kb_id}")
            print(f"   响应的 ID: {data['id']}")
            return False

        # 9. 验证知识库名称是否为空
        if not data['name'] or not data['name'].strip():
            print("❌ 错误：知识库名称为空")
            return False

        # 10. 成功验证
        print("✅ 结论：知识库有效")
        print(f"   知识库 ID: {data['id']}")
        print(f"   知识库名称: {data['name']}")
        print(f"   文档数量: {data.get('document_size', '未知')}")
        print(f"   总字数: {data.get('word_num', '未知')}")

        return True

    except requests.exceptions.Timeout:
        print("❌ 错误：请求超时（30秒）")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 错误：无法连接到服务器")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ 错误：请求异常 - {e}")
        return False
    except Exception as e:
        print(f"❌ 错误：未知异常 - {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("智谱托管知识库 ID 校验工具")
    print("=" * 60)

    is_valid = validate_knowledge_base()

    print("\n" + "=" * 60)
    if is_valid:
        print("🎉 校验通过：知识库 ID 有效")
        sys.exit(0)
    else:
        print("🚨 校验失败：知识库 ID 无效")
        sys.exit(1)