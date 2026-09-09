# main.py

import os
import requests
from datetime import datetime

def speak_text(text, api_key):
    url = "https://open.bigmodel.cn/api/paas/v4/audio/synthesis"
    headers = { "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = { "model": "glm-5.3", "text": text, "sample_rate": 16000}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["audio"]
    else:
        raise Exception(f"Failed to synthesize audio: {response.status_code}")

def transcribe_audio(audio, api_key):
    url = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"
    headers = { "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    data = { "audio": audio}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["text"]
    else:
        raise Exception(f"Failed to transcribe audio: {response.status_code}")

if __name__ == "__main__":
    api_key = os.environ['ZHIPUAI_API_KEY']
    text_to_speak = "发票需要在七个工作日内申请"
    try:
        audio = speak_text(text_to_speak, api_key)
        print(f"Original text: {text_to_speak}
Transcribed text: {transcribe_audio(audio, api_key)}")
    except Exception as e:
        print(f"Error: {e}")
