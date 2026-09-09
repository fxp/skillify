#!/usr/bin/env python3

import os
import requests

def classify_text(text):
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"]
    }
    data = {
        "model": "glm-4.6",
        "messages": [
            {
                "role": "user",
                "content": text
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()
    sentiment = None
    score = None
    for choice in result["choices"]:
        message = choice["message"]
        if "sentiment" in message:
            sentiment = message["sentiment"]
            score = float(message["score"])
            break
    return {
        "sentiment": sentiment,
        "score": score
    }

if __name__ == "__main__":
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]
    results = [classify_text(text) for text in texts]
    for result in results:
        print(result)