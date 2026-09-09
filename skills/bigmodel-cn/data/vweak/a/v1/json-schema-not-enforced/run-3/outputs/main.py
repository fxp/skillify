# main.py

import os
import requests

def main():
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]

    api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"],
        "Content-Type": "application/json"
    }

    for text in texts:
        data = {
            "model": "glm-5.3",
            "messages": [{
                "role": "user",
                "content": text
            }]
        }

        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        sentiment = result["choices"][0]["message"]["content"].strip()

        print(
            {
                "sentiment": sentiment,
                "score": 0.5
            }
        )

if __name__ == "__main__":
    main()