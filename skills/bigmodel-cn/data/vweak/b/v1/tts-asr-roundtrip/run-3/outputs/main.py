#!/usr/bin/env python3

import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 语音合成
def synthesize_speech(text):
    url = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "text": text
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['audio_url']
    else:
        raise Exception(f"Failed to synthesize speech: {response.status_code}")

# 语音识别
def recognize_speech(audio_url):
    url = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "audio_url": audio_url
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['text']
    else:
        raise Exception(f"Failed to recognize speech: {response.status_code}")

# 主函数
if __name__ == "__main__":
    text = "发票需要在七个工作日内申请"
    try:
        audio_url = synthesize_speech(text)
        print(f"Audio synthesized. URL: {audio_url}")
        recognized_text = recognize_speech(audio_url)
        print(f"Recognized text: {recognized_text}")
        if recognized_text == text:
            print("Voice link is working correctly.")
        else:
            print("Voice link is not working correctly.")
    except Exception as e:
        print(f"Error: {e}")
