#!/usr/bin/env python3
"""
使用 GLM Coding Plan 编程套餐额度进行图片识别的脚本
测试 invoice.png 图片的内容识别能力
"""

import os
import requests
import base64
from pathlib import Path

def encode_image_to_base64(image_path):
    """将图片编码为 base64"""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"无法读取图片文件: {e}")
        return None

def main():
    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误: 未找到环境变量 GLM_CODING_PLAN_API_KEY")
        print("请设置: export GLM_CODING_PLAN_API_KEY='your_key_here'")
        return

    # 检查图片文件
    image_path = Path('./invoice.png')
    if not image_path.exists():
        print(f"错误: 找不到图片文件 {image_path.absolute()}")
        print("请确保 invoice.png 在脚本同目录下")
        return

    # 编码图片
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        return

    # 构建请求数据
    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请详细描述这张发票图片中的内容，包括文字信息、表格数据、金额、日期等所有可见信息。"
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
        "stream": False
    }

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 发送请求
    print("正在调用 GLM Coding Plan API 进行图片识别...")
    try:
        # Coding Plan 的端点
        url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        # 解析响应
        data = response.json()

        # 打印模型信息
        print(f"\n{'='*50}")
        print(f"模型名称: {data.get('model', '未知')}")
        print(f"请求ID: {data.get('id', '未知')}")
        print(f"{'='*50}\n")

        # 打印识别结果
        if 'choices' in data and len(data['choices']) > 0:
            message = data['choices'][0]['message']
            content = message.get('content', '')

            if content:
                print("图片识别结果:")
                print("-" * 50)
                print(content)
            else:
                print("模型未返回内容")

            # 打印使用量信息
            if 'usage' in data:
                usage = data['usage']
                print(f"\n使用量统计:")
                print(f"提示词tokens: {usage.get('prompt_tokens', '未知')}")
                print(f"生成tokens: {usage.get('completion_tokens', '未知')}")
                print(f"总tokens: {usage.get('total_tokens', '未知')}")
        else:
            print("响应格式异常")
            print(f"完整响应: {data}")

    except requests.exceptions.HTTPError as http_err:
        error_data = http_err.response.json() if http_err.response.content else {}
        error_code = error_data.get('error', {}).get('code', '未知错误')
        error_msg = error_data.get('error', {}).get('message', '未知消息')

        print(f"HTTP错误: {http_err}")
        print(f"错误代码: {error_code}")
        print(f"错误信息: {error_msg}")

        # 特殊处理常见错误
        if error_code == '1113':
            print("\n分析: 这很可能是因为 Coding Plan 不支持视觉能力")
            print("根据文档，Coding Plan 只支持 glm-5.3 和 glm-5.3-flash 模型进行对话")
            print("但视觉能力可能不在套餐范围内，需要标准 API Key")

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()