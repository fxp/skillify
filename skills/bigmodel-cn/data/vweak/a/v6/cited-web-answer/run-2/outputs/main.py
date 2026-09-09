#!/usr/bin/env python3

import os
import requests

def ask_question():
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"],
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": "2026年智谱BigModel发布了哪些新模型"
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        answer = response.json()["choices"][0]["message"]["content"]
        sources = response.json().get("web_search", [])
        print(answer)
        print("Sources:")
        for source in sources:
            print("- " + source.get("title", "Unknown source") + " (" + source.get("link", "No link") + ")")
    else:
        print("Error fetching the answer.")

if __name__ == "__main__":
    ask_question()