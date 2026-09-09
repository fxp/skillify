#!/usr/bin/env python3
"""
智谱托管知识库ID验证脚本
用于验证配置中的知识库ID是否存在且可用，作为发布流水线的卡点检查
"""

import os
import sys
import requests
import json

def validate_zhipu_knowledge_base():
    """验证智谱托管知识库ID的有效性"""

    # 从环境变量读取配置
    kb_id = os.environ.get('ZHIPU_KB_ID')
    api_key = os.environ.get('ZHIPUAI_API_KEY')

    # 检查环境变量
    if not kb_id:
        print("❌ 验证失败：环境变量 ZHIPU_KB_ID 未设置")
        print("请确保配置文件中设置了 ZHIPU_KB_ID 环境变量")
        return False

    if not api_key:
        print("❌ 验证失败：环境变量 ZHIPUAI_API_KEY 未设置")
        print("请确保配置文件中设置了 ZHIPUAI_API_KEY 环境变量")
        return False

    print(f"🔍 开始验证知识库ID: {kb_id}")
    print("=" * 50)

    # API配置
    base_url = "https://open.bigmodel.cn/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 验证知识库是否存在 - 使用GET /knowledge/{id}接口
    validate_url = f"{base_url}/llm-application/open/knowledge/{kb_id}"

    try:
        print("正在调用知识库详情接口...")
        response = requests.get(validate_url, headers=headers)

        # 重要：知识库API的特性 - HTTP状态码可能是200，但实际结果在响应体的code字段里
        response_data = response.json()

        print(f"HTTP状态码: {response.status_code}")
        print(f"响应数据: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
        print("-" * 50)

        # 检查业务错误码
        if response.status_code != 200:
            print(f"❌ 验证失败：HTTP状态码 {response.status_code}")
            return False

        # 根据参考资料，知识库API返回200但业务码可能不是200
        if 'code' not in response_data:
            print("❌ 验证失败：响应中缺少code字段")
            return False

        if response_data['code'] == 200:
            print("✅ 验证成功：知识库存在且可用")

            # 尝试获取知识库的更多信息
            if 'data' in response_data:
                kb_data = response_data['data']
                print(f"📋 知识库名称: {kb_data.get('name', '未知')}")
                print(f"📊 文档数量: {kb_data.get('document_size', 0)}")
                print(f"📝 总字数: {kb_data.get('word_num', 0)}")
                print(f"🔤 分词后长度: {kb_data.get('length', 0)}")

                # 检查向量化模型
                embedding_id = kb_data.get('embedding_id')
                if embedding_id:
                    embedding_models = {
                        3: "Embedding-2",
                        11: "Embedding-3",
                        12: "Embedding-3-pro"
                    }
                    model_name = embedding_models.get(embedding_id, f"未知模型({embedding_id})")
                    print(f"🧠 向量化模型: {model_name}")

                return True
            else:
                print("✅ 验证成功：知识库存在，但无法获取详细信息")
                return True
        else:
            # 业务错误码处理
            error_code = response_data['code']
            error_msg = response_data.get('message', '未知错误')

            # 常见错误码处理
            if error_code == 100013:
                print(f"❌ 验证失败：知识库不存在 (错误码: {error_code})")
                print(f"错误信息: {error_msg}")
            elif error_code == 1000:
                print(f"❌ 验证失败：鉴权失败 (错误码: {error_code})")
                print(f"错误信息: {error_msg}")
                print("请检查API Key是否正确")
            elif error_code == 1214:
                print(f"❌ 验证失败：知识库ID参数非法 (错误码: {error_code})")
                print(f"错误信息: {error_msg}")
            else:
                print(f"❌ 验证失败：业务错误码 {error_code}")
                print(f"错误信息: {error_msg}")

            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ 验证失败：网络请求异常")
        print(f"错误详情: {str(e)}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ 验证失败：响应解析异常")
        print(f"错误详情: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ 验证失败：未知异常")
        print(f"错误详情: {str(e)}")
        return False

def main():
    """主函数"""
    print("🚀 智谱托管知识库ID验证工具")
    print("=" * 50)

    # 执行验证
    is_valid = validate_zhipu_knowledge_base()

    # 输出最终结论
    print("\n" + "=" * 50)
    if is_valid:
        print("🎉 校验结论：知识库有效，可以上线")
        print("✅ 发布流水线可以通过此检查点")
        sys.exit(0)
    else:
        print("🚨 校验结论：知识库无效，禁止上线")
        print("❌ 发布流水线被此检查点拦截")
        sys.exit(1)

if __name__ == "__main__":
    main()