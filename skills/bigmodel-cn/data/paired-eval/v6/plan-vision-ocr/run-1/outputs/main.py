#!/usr/bin/env python3
"""
使用GLM Coding Plan套餐额度识别发票图片内容
"""

import os
import requests
import json
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

def analyze_invoice_with_coding_plan():
    """使用GLM Coding Plan API分析发票图片"""

    # API配置
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
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

    # 构建请求数据
    # 尝试使用 glm-5.3-flash（支持视觉）
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

    # API端点 - 使用Coding Plan专用端点
    url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print("正在使用GLM Coding Plan套餐额度分析发票图片...")
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

        # 特定错误码处理
        if error_code == "1113":
            print("\n重要提示: 这是1113错误，说明套餐可能不支持视觉识别能力。")
            print("根据参考资料，GLM Coding Plan套餐只支持glm-5.3和glm-5.3-flash模型进行对话，")
            print("但不支持其他视觉模型如glm-4.6v、glm-5v-turbo等。")
            print("建议使用标准API Key调用专门的视觉模型。")
        elif error_code == "429":
            print("\n重要提示: 这是429错误，说明套餐额度可能已用完或该能力不在套餐范围内。")
            print("根据参考资料，GLM Coding Plan套餐不支持embeddings、rerank、images等能力。")
        elif "余额不足" in error_msg:
            print("\n重要提示: 这是余额不足错误，可能是因为:")
            print("1. 使用了错误的API端点（应使用/coding/paas/v4而不是/paas/v4）")
            print("2. 该能力不在套餐范围内")
            print("3. 套餐额度已用完")

    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    analyze_invoice_with_coding_plan()