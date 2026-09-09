# main.py

import os
import requests
import asyncio

# Set the API endpoint and model
API_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"

# Function to classify sentiment
async def classify_sentiment(text):
    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}"
    }
    data = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": text
        }],
    }
    response = await requests.post(API_ENDPOINT, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()
    return result['choices'][0]['message']['content']

# Function to run batch task
async def run_batch_task(texts):
    for text in texts:
        sentiment = await classify_sentiment(text)
        print(f"Text: {text}
Sentiment: {sentiment}")

# Main function
async def main):
    texts = [
        "I am happy",
        "I am sad",
        "I am neutral"
    ]
    await run_batch_task(texts)

# Print the model versions
print(f"I requested the model: {MODEL}")
model_response = await requests.get(f"https://open.bigmodel.cn/api/paas/v4/models/{MODEL}")
model_response.raise_for_status()
model_info = model_response.json()
print(f"The model actually used: {model_info['name']}\n{model_info['description']}\n{model_info['max_tokens']}\n{model_info['supportthinking']}\n{model_info['supporttools']}\n{model_info['supportimages']}\n{model_info['supportsounds']}\n{model_info['supportvideo']}\n{model_info['supportconversational']}")

# Run the main function
if __name__ == '__main__':
    asyncio.run(main())