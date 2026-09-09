# main.py

import os

import requests

def get_response(image_path):
    url = "https://open.bigmodel.cn/api/coding/paas/v4/ocr"
    headers = {
        "Authorization": "Bearer %s"
    }
    data = {
        "image": open(image_path, "rb").read()
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()

if __name__ == "__main__":
    image_path = "invoice.png"
    api_key = os.environ.get("GLM_CODING_PLAN_API_KEY")
    if not api_key:
        print("API Key not found.")
        exit(1)
    headers["Authorization"] = headers["Authorization"].replace("<API_KEY>", api_key)
    response = get_response(image_path)
    print("Model used: " + response["model"])
    print("Content recognized:")
    for text in response["texts"]:
        print(text)