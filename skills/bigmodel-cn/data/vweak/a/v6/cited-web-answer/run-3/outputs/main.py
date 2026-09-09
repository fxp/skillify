#!/usr/bin/env python3
import os
import requests

def ask_question():
    question = "2026年智谱BigModel发布了哪些新模型？"
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ['ZHIPUAI_API_KEY']
    }
    data = {
        "model": "glm-5.3",
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()['choices'][0]['message']['content']

if __name__ == '__main__':
    answer = ask_question()
    print(answer)
