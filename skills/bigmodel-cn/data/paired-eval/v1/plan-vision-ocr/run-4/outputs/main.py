#!/usr/bin/env python3
"""
GLM Coding Plan 视觉识别脚本
使用编程套餐额度识别 invoice.png 图片内容
"""

import os
import base64
import requests
from pathlib import Path

def encode_image(image_path):
    """将图片文件编码为 base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def main():
    # 检查环境变量
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件是否存在
    image_path = Path(__file__).parent / "invoice.png"
    if not image_path.exists():
        print(f"错误：找不到图片文件 {image_path}")
        return

    try:
        # 编码图片
        base64_image = encode_image(image_path)
        image_data_url = f"data:image/png;base64,{base64_image}"

        # 构建请求
        url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "glm-5.3-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请详细描述这张发票图片中的内容，包括：\n1. 发票基本信息（发票代码、发票号码、开票日期等）\n2. 买卖双方信息（销售方、购买方名称、税号等）\n3. 商品或服务信息（名称、规格、数量、单价、金额等）\n4. 税额信息\n5. 其他重要信息\n如果图片不清晰或信息难以辨认，请说明。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_data_url
                            }
                        }
                    ]
                }
            ],
            "stream": False,
            "max_tokens": 2048
        }

        print("正在调用 GLM Coding Plan API...")
        print(f"Base URL: {url}")
        print(f"Model: glm-5.3-flash")

        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印模型回答
        if "choices" in result and len(result["choices"]) > 0:
            answer = result["choices"][0]["message"]["content"]
            print("\n" + "="*50)
            print("模型回答：")
            print("="*50)
            print(answer)
        else:
            print("模型响应格式异常")

        # 打印使用的模型名（用于对账）
        print("\n" + "="*50)
        print("服务端使用的模型名：")
        print("="*50)
        print(f"{result.get('model', '未知模型')}")

        # 打印使用量信息（如果有）
        if "usage" in result:
            print("\n" + "="*50)
            print("Token 使用情况：")
            print("="*50)
            usage = result["usage"]
            print(f"输入 tokens: {usage.get('prompt_tokens', 0)}")
            print(f"输出 tokens: {usage.get('completion_tokens', 0)}")
            print(f"总 tokens: {usage.get('total_tokens', 0)}")

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "429" in error_msg and "1113" in error_msg:
            print("错误：套餐额度不足或资源包已用完")
            print("可能的原因：")
            print("1. 使用的模型不在套餐范围内")
            print("2. Base URL 配置错误（应使用 /coding/paas/v4）")
            print("3. 套餐额度已用完")
        else:
            print(f"请求失败: {error_msg}")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()