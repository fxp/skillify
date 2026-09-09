# main.py

import os
import requests

def analyze_sentiment(text):
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"]
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": text
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    result = response.json()
    sentiment_score = max(0, min(1, result["choices"][0]["confidence"]))
    if sentiment_score >= 0.7:
        return {
            "sentiment": "正面",
            "score": sentiment_score
        }
    elif sentiment_score >= 0.3:
        return {
            "sentiment": "中性",
            "score": sentiment_score
        }
    else:
        return {
            "sentiment": "负面",
            "score": sentiment_score
        }

if __name__ == "__main__":
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]
    for text in texts:
        print(analyze_sentiment(text))