# main.py
import os
import requests
import asyncio

async def main():
    api_key = os.environ['ZHIPUAI_API_KEY']
    url = "https://open.bigmodel.cn/api/paas/v4/async/chat/completions"
    messages = [
        "这句话很棒！",
        "这句话不好。",
        "这句话一般。"
    ]

    for message in messages:
        data = {
            "model": "glm-4.6",
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ]
        }

        async with requests.post(url, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, json=data) as response:
            print(response.json()["choices"][0]["message"]["content"])

    print("我请求的模型：glm-4.6")
    print("接口实际使用的模型：", response.json()["model"])