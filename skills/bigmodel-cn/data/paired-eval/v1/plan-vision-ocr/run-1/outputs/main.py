#!/usr/bin/env python3
import os
import base64
import requests
from pathlib import Path

def encode_image_to_base64(image_path):
    """将图片文件转换为 base64 编码"""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error reading image file: {e}")
        return None

def analyze_invoice_with_glm():
    """使用 GLM Coding Plan API 分析发票图片"""

    # 检查 API Key
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件
    current_dir = Path(__file__).parent
    image_path = current_dir / "invoice.png"

    if not image_path.exists():
        print(f"错误：找不到图片文件 {image_path}")
        return

    # 准备图片数据 - 使用 base64 方式
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        return

    # 构建 API 请求
    url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

    # 使用支持视觉的模型（实测套餐支持 glm-4.6v）
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 构建多模态请求体
    payload = {
        "model": "glm-4.6v",  # 使用视觉模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请仔细分析这张发票图片，提取并识别所有关键信息，包括但不限于：发票代码、发票号码、日期、购买方信息、销售方信息、商品/服务名称、金额、税率、价税合计等。请以结构化的方式清晰地列出所有识别出的信息。"
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
        "max_tokens": 2048,
        "temperature": 0.3,
        "stream": False
    }

    try:
        print("正在调用 GLM Coding Plan API 分析发票图片...")
        print(f"使用的模型: glm-4.6v")
        print(f"图片路径: {image_path}")
        print("-" * 50)

        # 发送请求
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印模型返回的实际模型名（用于对账）
        actual_model = result.get("model", "unknown")
        print(f"服务端实际使用的模型: {actual_model}")
        print("-" * 50)

        # 打印分析结果
        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0]["message"]
            content = message.get("content", "")

            if content:
                print("📋 发票分析结果:")
                print(content)
            else:
                print("模型返回内容为空")

            # 打印使用量统计
            if "usage" in result:
                usage = result["usage"]
                print("\n📊 Token 使用统计:")
                print(f"输入 tokens: {usage.get('prompt_tokens', 0)}")
                print(f"输出 tokens: {usage.get('completion_tokens', 0)}")
                print(f"总 tokens: {usage.get('total_tokens', 0)}")

                if 'prompt_tokens_details' in usage and 'cached_tokens' in usage['prompt_tokens_details']:
                    print(f"缓存命中 tokens: {usage['prompt_tokens_details']['cached_tokens']}")
        else:
            print("响应格式异常，无法获取结果")

    except requests.exceptions.HTTPError as e:
        error_code = e.response.status_code if e.response else "Unknown"
        error_msg = ""

        try:
            error_data = e.response.json()
            if "error" in error_data:
                error_msg = error_data["error"].get("message", "Unknown error")
        except:
            error_msg = e.response.text if e.response else str(e)

        print(f"HTTP 错误 ({error_code}): {error_msg}")

        # 根据常见错误码给出具体建议
        if error_code == 429:
            print("\n可能的原因：")
            print("1. 套餐额度已用尽 - 请等待额度重置或检查套餐状态")
            print("2. 请求频率过高 - 请降低请求频率")
            print("3. 模型不在套餐支持范围内 - 尝试使用 glm-4.6v 或 glm-5v-turbo")
        elif error_code == 401:
            print("\n请检查 GLM_CODING_PLAN_API_KEY 是否正确设置")
        elif error_code == 400:
            print("\n请求参数可能有误，请检查:")
            print("- 图片格式是否正确（仅支持 png/jpeg/jpg）")
            print("- 图片大小是否超过限制（单图 ≤5M，像素 ≤6000×6000）")
            print("- 模型名称是否正确（建议使用 glm-4.6v）")

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
        print("\n可能的解决方案:")
        print("1. 检查网络连接")
        print("2. 检查防火墙设置")
        print("3. 检查代理配置（如果使用代理）")

    except Exception as e:
        print(f"发生未知错误: {e}")

if __name__ == "__main__":
    analyze_invoice_with_glm()