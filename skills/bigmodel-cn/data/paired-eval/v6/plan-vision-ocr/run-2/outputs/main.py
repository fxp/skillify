#!/usr/bin/env python3
"""
使用 GLM Coding Plan 编程套餐识别发票图片内容
"""

import os
import base64
import requests
import json
from pathlib import Path

def encode_image(image_path):
    """将图片文件编码为 base64"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def main():
    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件是否存在
    image_path = Path(__file__).parent / "invoice.png"
    if not image_path.exists():
        print(f"错误：图片文件 {image_path} 不存在")
        return

    # 编码图片
    image_base64 = encode_image(image_path)

    # API 配置
    base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
    model = "glm-5.3-flash"  # 使用视觉模型

    # 构建请求
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 准备图片数据
    image_data = f"data:image/png;base64,{image_base64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请仔细分析这张发票图片，提取并识别其中的所有文本信息，包括但不限于：\n1. 发票号码\n2. 开票日期\n3. 购买方名称、纳税人识别号、地址电话、开户行及账号\n4. 销售方名称、纳税人识别号、地址电话、开户行及账号\n5. 商品或服务名称、规格型号、单位、数量、单价、金额、税率、税额\n6. 价税合计（大写和小写）\n7. 备注\n\n请按照结构化的方式整理这些信息。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
        "stream": False
    }

    print("正在调用 GLM Coding Plan API 进行发票识别...")

    try:
        # 发送请求
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        # 检查响应状态
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印服务端实际使用的模型名
        print("\n" + "="*50)
        print(f"服务端实际使用的模型: {result.get('model', 'unknown')}")
        print("="*50)

        # 打印识别结果
        if 'choices' in result and len(result['choices']) > 0:
            content = result['choices'][0]['message']['content']
            print("\n📋 发票识别结果：")
            print("-"*50)
            print(content)
        else:
            print("错误：API 返回的响应格式不正确")
            print(f"完整响应: {json.dumps(result, indent=2, ensure_ascii=False)}")

        # 打印 token 使用情况
        if 'usage' in result:
            usage = result['usage']
            print("\n💰 Token 使用情况：")
            print(f"- 输入 tokens: {usage.get('prompt_tokens', 0)}")
            print(f"- 输出 tokens: {usage.get('completion_tokens', 0)}")
            print(f"- 总 tokens: {usage.get('total_tokens', 0)}")

    except requests.exceptions.HTTPError as e:
        error_msg = e.response.text
        print(f"HTTP 错误: {e.response.status_code}")

        # 检查是否是 1113 错误（余额不足）
        if '1113' in error_msg:
            print("❌ 错误：套餐额度不足或无可用资源包")
            print("这可能是因为：")
            print("1. 使用的模型不在编程套餐范围内")
            print("2. 打错了端点（应该用 /api/coding/paas/v4 而不是 /api/paas/v4）")
            print("3. 套餐额度已用完")
        elif '429' in error_msg:
            print("❌ 错误：请求频率过高或套餐额度不足")
        else:
            print(f"❌ 错误详情: {error_msg}")

    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")

if __name__ == "__main__":
    main()