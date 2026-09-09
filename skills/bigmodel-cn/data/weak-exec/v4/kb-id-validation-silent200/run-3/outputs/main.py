#!/usr/bin/env python3
"""
智谱AI知识库ID校验脚本
用于验证配置中的知识库ID是否存在且可用

使用方法：
export ZHIPU_KB_ID=your_knowledge_base_id
export ZHIPUAI_API_KEY=your_api_key
python3 main.py
"""

import os
import sys
import requests
import json

# API配置
BASE_URL = "https://open.bigmodel.cn/api"
KB_CHECK_ENDPOINT = "/llm-application/open/knowledge/{kb_id}"

def check_knowledge_base(kb_id, api_key):
    """
    校验知识库是否存在

    Args:
        kb_id (str): 知识库ID
        api_key (str): API密钥

    Returns:
        dict: 包含校验结果和详细信息的字典
    """
    url = BASE_URL + KB_CHECK_ENDPOINT.format(kb_id=kb_id)

    try:
        # 发送请求
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )

        # 智谱知识库API的特殊处理：HTTP状态码可能为200，但真实结果在响应体的code里
        response_data = response.json()

        # 检查API返回的状态码
        if response_data.get("code") == 200:
            # 知识库存在且可用
            kb_info = response_data.get("data", {})
            return {
                "valid": True,
                "message": "知识库存在且可用",
                "knowledge_base": {
                    "id": kb_id,
                    "name": kb_info.get("name", ""),
                    "embedding_id": kb_info.get("embedding_id", ""),
                    "contextual": kb_info.get("contextual", ""),
                    "document_size": kb_info.get("document_size", 0),
                    "length": kb_info.get("length", 0),
                    "word_num": kb_info.get("word_num", 0)
                },
                "raw_response": response_data
            }
        elif response_data.get("code") == 100013:
            # 知识库不存在
            return {
                "valid": False,
                "message": "知识库不存在",
                "error_code": 100013,
                "error_message": response_data.get("message", ""),
                "raw_response": response_data
            }
        else:
            # 其他错误
            return {
                "valid": False,
                "message": f"校验失败，错误码：{response_data.get('code')}",
                "error_code": response_data.get("code"),
                "error_message": response_data.get("message", ""),
                "raw_response": response_data
            }

    except requests.exceptions.RequestException as e:
        # 网络请求异常
        return {
            "valid": False,
            "message": f"请求失败：{str(e)}",
            "error_type": "request_error"
        }
    except json.JSONDecodeError as e:
        # JSON解析异常
        return {
            "valid": False,
            "message": f"响应解析失败：{str(e)}",
            "error_type": "json_error"
        }
    except Exception as e:
        # 其他未知异常
        return {
            "valid": False,
            "message": f"未知错误：{str(e)}",
            "error_type": "unknown_error"
        }

def main():
    """主函数"""
    # 从环境变量读取配置
    kb_id = os.environ.get("ZHIPU_KB_ID")
    api_key = os.environ.get("ZHIPUAI_API_KEY")

    # 检查环境变量
    if not kb_id:
        print("错误：未设置环境变量 ZHIPU_KB_ID")
        sys.exit(1)

    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY")
        sys.exit(1)

    print(f"开始校验知识库ID: {kb_id}")
    print("=" * 50)

    # 执行校验
    result = check_knowledge_base(kb_id, api_key)

    # 打印结果
    if result["valid"]:
        print("\n✅ 校验结果：知识库有效")
        print("\n知识库详情：")
        kb = result["knowledge_base"]
        print(f"  ID: {kb['id']}")
        print(f"  名称: {kb['name']}")
        print(f"  向量化模型ID: {kb['embedding_id']}")
        print(f"  上下文增强: {'是' if kb['contextual'] == 1 else '否'}")
        print(f"  文档数量: {kb['document_size']}")
        print(f"  总长度: {kb['length']}")
        print(f"  总字数: {kb['word_num']}")
    else:
        print("\n❌ 校验结果：知识库无效")
        print(f"  错误信息: {result['message']}")
        if "error_code" in result:
            print(f"  错误码: {result['error_code']}")
            print(f"  详细信息: {result['error_message']}")

        # 退出码1表示校验失败，用于CI/CD流水线卡点
        sys.exit(1)

    print("=" * 50)
    print("校验完成")

if __name__ == "__main__":
    main()