import os
import requests
import base64
from pathlib import Path

def main():
    # 检查环境变量
    api_key = os.environ.get('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查图片文件是否存在
    image_path = Path(__file__).parent / "invoice.png"
    if not image_path.exists():
        print(f"错误：找不到图片文件 {image_path}")
        return

    # 读取图片并转换为 base64
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_url = f"data:image/png;base64,{image_base64}"
    except Exception as e:
        print(f"读取图片失败: {e}")
        return

    # 构建请求
    url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-5.3-flash",  # 使用支持视觉的模型
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请详细识别并描述这张图片中的内容，包括文字、表格、图像等所有元素。如果这是发票，请提取出发票的关键信息如发票代码、发票号码、日期、金额、买卖双方信息等。"
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
        "max_tokens": 4096,
        "temperature": 0.3,
        "stream": False
    }

    try:
        # 发送请求
        print("正在调用 GLM Coding Plan API 进行图像识别...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        # 解析响应
        result = response.json()

        # 打印模型信息（用于对账）
        model_used = result.get("model", "unknown")
        print(f"\n=== 服务端实际使用的模型：{model_used} ===\n")

        # 打印识别结果
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            print("=== 图像识别结果 ===")
            print(content)
        else:
            print("未能获取到识别结果")
            print(f"完整响应: {result}")

        # 打印使用统计（如果有）
        if "usage" in result:
            usage = result["usage"]
            print(f"\n=== 使用统计 ===")
            print(f"输入 Token 数: {usage.get('prompt_tokens', 0)}")
            print(f"输出 Token 数: {usage.get('completion_tokens', 0)}")
            print(f"总计 Token 数: {usage.get('total_tokens', 0)}")
            if 'cached_tokens' in usage.get('prompt_tokens_details', {}):
                print(f"缓存命中 Token 数: {usage['prompt_tokens_details']['cached_tokens']}")

    except requests.exceptions.HTTPError as e:
        error_code = e.response.status_code
        error_msg = e.response.text

        print(f"HTTP 错误 [{error_code}]: {error_msg}")

        # 根据错误码判断是否是套餐不支持视觉能力
        if error_code == 429:
            if "余额不足" in error_msg or "1113" in error_msg:
                print("\n=== 判断结果 ===")
                print("错误 429 + 余额不足/1113 可能的原因：")
                print("1. 您的 GLM Coding Plan 套餐可能不支持图像识别能力")
                print("2. 套餐额度已用完")
                print("3. 请求的模型不在套餐支持范围内")
                print("\n依据：根据文档，GLM Coding Plan 只支持文本对话和网页阅读，")
                print("图像识别、embeddings、rerank 等能力需要使用标准 API Key")
            else:
                print("\n=== 判断结果 ===")
                print("可能是其他类型的 429 错误（如并发限制）")
        else:
            print(f"\n其他 HTTP 错误: {error_msg}")

    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    main()