# main.py
import os
import requests

def sentiment_analysis(texts):
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"],
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": text
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]

if __name__ == "__main__":
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]
    for text in texts:
        print(sentiment_analysis(text))