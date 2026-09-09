#!/usr/bin/env python3

import os
import requests
from hashlib import md5

# 读取 API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 要合成的文本
text_to合成 = "发票需要在七个工作日内申请"

# 语音合成 API 地址
tts_api_url = "https://open.bigmodel.cn/api/paas/v4/audio/speech"

# 语音识别 API 地址
asr_api_url = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"

# 语音合成请求参数
tts_data = {
    "model": "glm-5.3",
    "text": text_to合成,
    "voice_name": "male1",
    "sample_rate": 16000,
    "lang": "zh"
}

# 语音合成请求头
tts_headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# 发送语音合成请求
response = requests.post(tts_api_url, headers=tts_headers, json=tts_data)
response.raise_for_status()
audio_url = response.json()['audio_url']

# 下载合成音频
audio_response = requests.get(audio_url)
with open('synthesized_audio.mp3', 'wb') as audio_file:
    audio_file.write(audio_response.content)

# 语音识别请求参数
asr_data = {
    "model": "glm-5.3",
    "audio": open('synthesized_audio.mp3', 'rb').read(),
    "lang": "zh"
}

# 语音识别请求头
asr_headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

# 发送语音识别请求
asr_response = requests.post(asr_api_url, headers=asr_headers, json=asr_data)
asr_response.raise_for_status()
asr_result = asr_response.json()['result']

# 打印识别结果并比对原文
print(f"原文: {text_to合成}")
print(f"识别结果: {asr_result}")
if text_to合成 == asr_result:
    print("语音链路打通成功！")
else:
    print("语音链路未打通，识别结果与原文不匹配。")
