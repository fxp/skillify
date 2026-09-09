#!/usr/bin/env python3

import os
import requests

def fetch_answer(question):
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": question
        }],
        "stream": false
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]

if __name__ == "__main__":
    question = "2026 年智谱 BigModel 发布了哪些新模型"
    answer = fetch_answer(question)
    print(answer)