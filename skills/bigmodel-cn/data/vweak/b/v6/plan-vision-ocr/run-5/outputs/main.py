#!/usr/bin/env python3
import os
import requests

# 获取 API Key
api_key = os.environ['GLM_CODING_PLAN_API_KEY']

# 基础 URL
base_url = 'https://open.bigmodel.cn/api/coding/paas/v4'

# 模型名
model_name = 'glm-5.3'

# 图像路径
image_path = 'invoice.png'

# 获取图像内容
def get_image_content(image_path):
    with open(image_path, 'rb') as f:
        return f.read()

# 调用 API 并打印结果
def call_api(image_content):
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': model_name,
        'image': {'content': image_content}
    }
    response = requests.post(f'{base_url}/images/analyze', headers=headers, json=data)
    if response.status_code == 200:
        print(response.json())
    else:
        print('Error:', response.status_code)

# 主函数
if __name__ == '__main__':
    image_content = get_image_content(image_path)
    call_api(image_content)
