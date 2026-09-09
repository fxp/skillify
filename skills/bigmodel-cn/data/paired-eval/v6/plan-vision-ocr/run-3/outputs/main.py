#!/usr/bin/env python3
"""
使用 GLM Coding Plan 编程套餐额度识别 invoice.png 图片内容
"""

import os
import requests
import json

def main():
    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件是否存在
    image_path = 'invoice.png'
    if not os.path.exists(image_path):
        print(f"错误：找不到图片文件 {image_path}")
        return

    # 编码图片为 base64
    try:
        with open(image_path, 'rb') as f:
            image_base64 = f.read()
    except Exception as e:
        print(f"读取图片文件失败：{e}")
        return

    # 将 base64 编码的图片转换为 data URI
    image_data_url = f"data:image/png;base64,{image_base64.decode('utf-8')}"

    # Coding Plan 的 API 端点
    url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

    # 请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 请求体
    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请详细分析这张发票图片的内容，包括：\n1. 发票的基本信息（发票代码、发票号码、日期等）\n2. 买卖双方信息（销售方名称、购买方名称等）\n3. 商品或服务清单（名称、规格、单位、数量、单价、金额等）\n4. 金额总计（含税价、税额等）\n5. 其他重要信息"
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
        "max_tokens": 2000,  # 足够的输出长度
        "temperature": 0.3,  # 较低的温度，更稳定的结果
        "stream": False
    }

    try:
        print("正在发送请求...")
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()

        response_data = resp.json()

        # 获取模型回答
        if 'choices' in response_data and len(response_data['choices']) > 0:
            answer = response_data['choices'][0]['message']['content']
            print("\n=== 模型回答 ===")
            print(answer)
        else:
            print("错误：响应中没有找到有效内容")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))

        # 打印服务端实际使用的模型名
        actual_model = response_data.get('model', '未知')
        print(f"\n=== 服务端实际使用的模型 ===")
        print(actual_model)

        # 打印使用统计
        if 'usage' in response_data:
            usage = response_data['usage']
            print(f"\n=== Token 使用统计 ===")
            print(f"输入 tokens: {usage.get('prompt_tokens', 0)}")
            print(f"输出 tokens: {usage.get('completion_tokens', 0)}")
            print(f"总计 tokens: {usage.get('total_tokens', 0)}")

    except requests.exceptions.HTTPError as e:
        error_data = e.response.json() if e.response.content else {}
        error_code = error_data.get('error', {}).get('code', '未知错误码')
        error_msg = error_data.get('error', {}).get('message', '未知错误')

        print(f"\n=== HTTP 错误 {e.response.status_code} ===")
        print(f"错误码: {error_code}")
        print(f"错误信息: {error_msg}")

        # 如果是 1113 错误，说明套餐确实不能用视觉能力
        if error_code == '1113':
            print("\n=== 结论 ===")
            print("错误码 1113 表示套餐额度不足或该能力不在套餐范围内。")
            print("根据 GLM Coding Plan 文档，视觉理解能力不在套餐支持范围内，")
            print("需要使用标准 API Key 和 /paas/v4 端点才能使用视觉能力。")

    except Exception as e:
        print(f"\n=== 其他错误 ===")
        print(f"错误信息: {str(e)}")

if __name__ == "__main__":
    main()