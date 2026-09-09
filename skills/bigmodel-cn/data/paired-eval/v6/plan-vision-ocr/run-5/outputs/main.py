#!/usr/bin/env python3
import os
import base64
import requests
import json
from pathlib import Path

def main():
    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件是否存在
    image_path = Path('invoice.png')
    if not image_path.exists():
        print("错误：同目录下没有找到 invoice.png 文件")
        return

    # 读取图片并转换为 Base64
    try:
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # 构建请求
            url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # 准备图片的 data URL
            image_url = f"data:image/png;base64,{base64_image}"

            # 构建请求体，使用视觉模型 glm-5.3-flash
            payload = {
                "model": "glm-5.3-flash",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请仔细分析这张图片中的内容，描述你看到的所有信息，包括文字、数字、格式等。"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.3
            }

            print("正在发送请求...")
            print(f"使用的模型: glm-5.3-flash")
            print(f"图片大小: {len(image_data)} bytes")
            print("-" * 50)

            # 发送请求
            response = requests.post(url, headers=headers, json=payload, timeout=60)

            # 检查响应
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}")
                try:
                    error_info = response.json()
                    print(f"错误信息: {json.dumps(error_info, ensure_ascii=False, indent=2)}")
                    if response.status_code == 429:
                        print("\n可能的错误原因:")
                        print("1. Base URL 错误 - 当前使用的是编程套餐端点 /api/coding/paas/v4")
                        print("2. 模型不支持 - 套餐可能不支持视觉能力")
                        print("3. 额度不足 - 套餐额度已用完")
                        print("4. API Key 不匹配 - 请确认是 GLM Coding Plan 的 Key")
                except:
                    print(f"错误响应: {response.text}")
                return

            # 解析响应
            result = response.json()

            # 获取实际使用的模型名
            used_model = result.get('model', '未知模型')

            print("服务端实际使用的模型:", used_model)
            print("-" * 50)

            # 获取模型回答
            if 'choices' in result and len(result['choices']) > 0:
                message = result['choices'][0]['message']
                content = message.get('content', '')

                if content:
                    print("模型识别结果:")
                    print(content)
                else:
                    print("模型返回内容为空")
            else:
                print("响应格式异常，未找到有效的回答")

            # 打印 token 使用情况
            if 'usage' in result:
                usage = result['usage']
                print("\nToken 使用情况:")
                print(f"输入 tokens: {usage.get('prompt_tokens', 0)}")
                print(f"输出 tokens: {usage.get('completion_tokens', 0)}")
                print(f"总计 tokens: {usage.get('total_tokens', 0)}")

            # 尝试获取请求 ID 用于对账
            if 'request_id' in result:
                print(f"\n请求 ID (用于对账): {result['request_id']}")

    except Exception as e:
        print(f"发生错误: {str(e)}")
        print("\n根据 GLM Coding Plan 的说明，如果套餐确实不支持视觉能力，可能的原因包括:")
        print("1. 套餐只支持 glm-5.3 和 glm-5.3-flash 的基础对话能力")
        print("2. 视觉能力需要使用标准 API，不在套餐范围内")
        print("3. 需要使用标准 API Key 和 /api/paas/v4 端点")
        print("4. 建议查看套餐文档确认可用能力范围")

if __name__ == "__main__":
    main()