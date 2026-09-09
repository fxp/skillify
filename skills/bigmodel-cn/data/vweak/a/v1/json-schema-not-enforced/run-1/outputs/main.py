import os
import requests

def get_sentiment(text):
    api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": text
        }],
        "stream": False
    }
    response = requests.post(api_url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()
    sentiment = result['choices'][0]['message']['content']
    return sentiment

if __name__ == '__main__':
    texts = [
        "这家店服务太差了，再也不来了",
        "东西还行吧，没什么特别的",
        "太惊喜了，比我预期好太多，强烈推荐"
    ]
    for text in texts:
        sentiment = get_sentiment(text)
        print(f"{text} -> {sentiment}")