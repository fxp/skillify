#!/usr/bin/env python3
"""
使用 GLM Coding Plan 套餐额度识别发票图片内容
"""

import os
import requests
from base64 import b64encode
import json

def encode_image_to_base64(image_path):
    """将图片编码为 base64"""
    try:
        with open(image_path, "rb") as image_file:
            return b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"读取图片失败: {e}")
        return None

def analyze_invoice_with_coding_plan():
    """使用编程套餐API识别发票内容"""

    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误: 请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件
    image_path = "invoice.png"
    if not os.path.exists(image_path):
        print(f"错误: 找不到图片文件 {image_path}")
        return

    # 编码图片
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        return

    # API 配置
    base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
    url = f"{base_url}/chat/completions"

    # 准备请求数据
    payload = {
        "model": "glm-5.3-flash",  # 编程套餐支持且具备视觉能力的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请仔细分析这张发票图片，提取并识别其中的所有关键信息，包括但不限于：发票号码、开票日期、购买方信息、销售方信息、商品/服务名称、金额、税率等。请以结构化的方式输出这些信息。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000,
        "stream": False
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print("正在发送请求...")

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印模型名（用于对账）
        print("\n" + "="*50)
        print(f"【对账信息】实际使用的模型: {result.get('model', '未知')}")
        print("="*50 + "\n")

        # 打印模型回答
        if 'choices' in result and len(result['choices']) > 0:
            message = result['choices'][0]['message']
            content = message.get('content', '没有获取到回答内容')

            print("\n【模型回答】")
            print("-" * 50)
            print(content)
            print("-" * 50 + "\n")

            # 如果有思考内容，也打印出来
            if 'reasoning_content' in message:
                print("\n【思考过程】")
                print("-" * 50)
                print(message['reasoning_content'])
                print("-" * 50 + "\n")
        else:
            print("错误: 响应格式不正确")
            print(json.dumps(result, indent=2, ensure_ascii=False))

        # 打印使用情况
        if 'usage' in result:
            print("\n【Token使用情况】")
            print("-" * 50)
            usage = result['usage']
            print(f"输入Token数: {usage.get('prompt_tokens', 0)}")
            print(f"输出Token数: {usage.get('completion_tokens', 0)}")
            print(f"总Token数: {usage.get('total_tokens', 0)}")
            if 'reasoning_tokens' in usage:
                print(f"思考Token数: {usage['reasoning_tokens']}")
            print("-" * 50 + "\n")

    except requests.exceptions.HTTPError as http_err:
        error_data = http_err.response.json() if http_err.response else {}
        error_code = error_data.get('error', {}).get('code', '未知错误码')
        error_message = error_data.get('error', {}).get('message', '未知错误')

        print(f"\nHTTP错误: {http_err}")
        print(f"错误码: {error_code}")
        print(f"错误信息: {error_message}")

        # 特殊处理套餐相关的错误
        if error_code == '1113':
            print("\n【重要提示】")
            print("错误码1113表示'余额不足或无可用资源包'。")
            print("这可能是因为：")
            print("1. 使用了编程套餐Key但打到了标准API端点")
            print("2. 当前请求的能力不在套餐范围内")
            print("3. 套餐额度已用完")
            print("\n根据文档，glm-5.3-flash模型在编程套餐中应该是支持的。")
            print("如果仍有此错误，建议：")
            print("- 确认GLM_CODING_PLAN_API_KEY环境变量设置正确")
            print("- 检查是否真的只有编程套餐Key（标准API Key无法使用套餐额度）")

    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    analyze_invoice_with_coding_plan()