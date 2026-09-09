#!/usr/bin/env python3

import os
import requests

def fetch_text_from_knowledge_base(question):
    url = "https://open.bigmodel.cn/api/paas/v4/knowledge/search"
    headers = {
        "Authorization": "Bearer " + os.environ["ZHIPUAI_API_KEY"],
        "Content-Type": "application/json"
    }
    data = {
        "model": "glm-5.3",
        "messages": [{
            "role": "user",
            "content": question
        }]
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["results"][0]["document"]["content"]
    else:
        return "No results found"

if __name__ == "__main__":
    with open("faq.txt", "r", encoding="utf-8") as file:
        for line in file:
            question = line.strip().strip("\n")
            print("Question: " + question)
            print("Answer: " + fetch_text_from_knowledge_base(question))
