# main.py

import asyncio
import requests
import os

# 检查模型版本
async def check_model_version(api_key):
    url = "https://api.bigmodel.cn/v1.0/check-model-version"
    headers = {
        "Authorization": "Bearer " + api_key
    }
    response = await requests.get(url, headers=headers)
    if response.status_code == 200:
        model_info = response.json()
        print("我请求的模型：", model_info["model"])
        print("接口实际使用的模型：", model_info["used_model"])
        if model_info["model"] != model_info["used_model"]:
            raise Exception("模型版本不一致！")
    else:
        raise Exception("检查模型版本失败！")

# 批量任务：对三句话做情感分类
async def emotion_classification(api_key):
    sentences = [
        "我非常喜欢这个产品",
        "这个产品太糟糕了",
        "这个产品一般般"
    ]
    results = []
    for sentence in sentences:
        url = "https://api.bigmodel.cn/v1.0/async/chat/completions"
        headers = {
            "Authorization": "Bearer " + api_key
        }
        data = {
            "text": sentence
        }
        response = await requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            results.append((sentence, result["text"]))
        else:
            raise Exception("情感分类失败！")
    return results

if __name__ == "__main__":
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    asyncio.run(check_model_version(api_key))
    results = asyncio.run(emotion_classification(api_key))
    for sentence, result in results:
        print(f"{sentence}: {result}")
