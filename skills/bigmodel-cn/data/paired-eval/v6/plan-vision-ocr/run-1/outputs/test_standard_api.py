#!/usr/bin/env python3
"""
测试标准API（非Coding Plan）用于视觉识别的对比脚本
"""

import os
import requests
import base64
from pathlib import Path

def encode_image_to_base64(image_path):
    """将图片文件编码为base64"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image: {e}")
        return None

def analyze_invoice_with_standard_api():
    """使用标准API分析发票图片（仅用于对比测试）"""

    # API配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")  # 标准API Key
    if not api_key:
        print("警告：未设置标准API Key环境变量 ZHIPUAI_API_KEY")
        print("这个脚本仅用于对比测试，不会消耗Coding Plan额度")
        return

    # 检查图片文件是否存在
    invoice_path = "invoice.png"
    if not Path(invoice_path).exists():
        print(f"错误：找不到图片文件 {invoice_path}")
        return

    # 编码图片
    base64_image = encode_image_to_base64(invoice_path)
    if not base64_image:
        return

    # 构建请求数据 - 使用glm-5.3-flash（支持视觉）
    payload = {
        "model": "glm-5.3-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请详细分析这张发票图片，提取所有关键信息包括：发票代码、发票号码、开票日期、购买方信息、销售方信息、商品/服务名称、规格型号、单位、数量、单价、金额、税率、税额等。如果图片不是发票，请说明图片内容。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
        "stream": False
    }

    # API端点 - 标准API端点
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print("使用标准API（非Coding Plan）测试视觉识别能力...")
    print(f"使用的模型: glm-5.3-flash")
    print("-" * 50)

    try:
        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印模型实际使用的名称
        if "model" in result:
            print(f"服务端实际使用的模型: {result['model']}")
            print("-" * 50)

        # 打印分析结果
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            print("发票内容分析结果:")
            print(content)

            # 打印使用情况（如果有）
            if "usage" in result:
                usage = result["usage"]
                print("\n" + "-" * 50)
                print("Token使用情况:")
                print(f"输入tokens: {usage.get('prompt_tokens', 'N/A')}")
                print(f"输出tokens: {usage.get('completion_tokens', 'N/A')}")
                print(f"总tokens: {usage.get('total_tokens', 'N/A')}")

    except requests.exceptions.HTTPError as http_err:
        error_data = http_err.response.json() if http_err.response.content else {}
        error_code = error_data.get("error", {}).get("code", "Unknown")
        error_msg = error_data.get("error", {}).get("message", "Unknown error")

        print(f"HTTP错误: {error_code}")
        print(f"错误信息: {error_msg}")

    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    analyze_invoice_with_standard_api()