import os
import requests
import base64
import json
from pathlib import Path

def main():
    # 获取 GLM Coding Plan API Key
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 GLM_CODING_PLAN_API_KEY")
        return

    # 检查 invoice.png 是否存在
    invoice_path = Path(__file__).parent / "invoice.png"
    if not invoice_path.exists():
        print("错误：在脚本同目录下未找到 invoice.png 文件")
        return

    # 将图片转换为 base64
    with open(invoice_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')

    # 构建请求
    url = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 使用 glm-5.3-flash 模型（支持多模态）
    payload = {
        "model": "glm-5.3-flash",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "请详细描述这张图片中的内容，包括文字信息、表格数据、发票类型、金额等所有你能看到的信息。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2000,
        "temperature": 0.3
    }

    try:
        print("正在发送请求...")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()

        # 打印模型回答
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            print("\n=== 模型回答 ===")
            print(content)
        else:
            print("\n错误：响应中没有找到有效的回答")

        # 打印实际使用的模型名（用于对账）
        actual_model = result.get("model", "未知")
        print(f"\n=== 对账信息 ===")
        print(f"实际使用的模型: {actual_model}")

        # 打印使用情况
        if "usage" in result:
            usage = result["usage"]
            print(f"输入Token数: {usage.get('prompt_tokens', 0)}")
            print(f"输出Token数: {usage.get('completion_tokens', 0)}")
            print(f"总Token数: {usage.get('total_tokens', 0)}")

    except requests.exceptions.HTTPError as http_err:
        error_data = http_err.response.json() if http_err.response.content else {}
        error_code = error_data.get("error", {}).get("code", "未知错误")
        error_msg = error_data.get("error", {}).get("message", "未知错误信息")

        print(f"\nHTTP错误: {error_code} - {error_msg}")

        # 特殊判断套餐是否支持视觉能力
        if error_code == "1113":
            print("\n=== 重要提示 ===")
            print("错误代码 1113 可能意味着：")
            print("1. 您的 GLM Coding Plan 套餐不支持视觉能力")
            print("2. 您可能使用了错误的端点或模型")
            print("3. 您的套餐额度已用尽")
            print("\n根据官方文档，GLM Coding Plan 只支持以下能力：")
            print("- 文本对话（glm-5.3、glm-5.3-flash）")
            print("- 网页阅读（reader 接口）")
            print("- 函数调用（tools）")
            print("\n纯视觉模型（如 glm-4.6v）不在套餐范围内，需要使用标准 API Key。")

    except requests.exceptions.RequestException as req_err:
        print(f"\n请求异常: {req_err}")
    except json.JSONDecodeError as json_err:
        print(f"\nJSON解析错误: {json_err}")
    except Exception as e:
        print(f"\n未知错误: {e}")

if __name__ == "__main__":
    main()