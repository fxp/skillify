# main.py
import os
import requests

def sentiment_classification(texts):
    api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    api_key = os.environ['ZHIPUAI_API_KEY']
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
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
    sentiment = result['choices'][0]['message']['content']
    score = float(result['choices'][0]['confidence'])
    return {
        "sentiment": sentiment,
        "score": score
    }

if __name__ == '__main__':
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]
    for text in texts:
        print(sentiment_classification(text))
