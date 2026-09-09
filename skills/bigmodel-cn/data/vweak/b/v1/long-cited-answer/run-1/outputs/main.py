# main.py

import os
import requests

def fetch_news(url):
    headers = {
        "Authorization": "Bearer " + os.environ['ZHIPUAI_API_KEY'],
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return None

if __name__ == "__main__":
    url = "https://open.bigmodel.cn/api/v4/news/search?query=2026年中国新能源汽车出口的主要目的地国家"
    news_data = fetch_news(url)
    if news_data:
        print(news_data)
    else:
        print("Failed to fetch news data.")
