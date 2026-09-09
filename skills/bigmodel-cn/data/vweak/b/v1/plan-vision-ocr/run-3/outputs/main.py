import requests

import sys
import os


def main():
    # 从环境变量获取API Key
    api_key = os.getenv('GLM_CODING_PLAN_API_KEY')
    if not api_key:
        print("未找到API Key，请确保GLM_CODING_PLAN_API_KEY环境变量已设置。")
        return

    # 图片文件路径
    image_path = 'invoice.png'
    if not os.path.exists(image_path):
        print(f"未找到图片文件：{image_path}")
        return

    # 构建请求URL
    url = "https://api.zhipu.ai/v1/recognize"
    files = {'file': open(image_path, 'rb')}

    # 设置请求头部
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'multipart/form-data'
    }

    try:
        # 发送请求
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()  # 如果请求失败，抛出异常

        # 打印结果
        print("服务端实际使用的模型名：", response.json().get('model_name'))
        print("模型回答：", response.json().get('text'))

    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 401:
            print("认证失败：API Key无效或已过期。")
        else:
            print("HTTP错误：", err)
    except Exception as err:
        print("其他错误：", err)

if __name__ == "__main__":
    main()