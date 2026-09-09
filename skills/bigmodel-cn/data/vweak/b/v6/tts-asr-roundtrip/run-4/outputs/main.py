#!/usr/bin/env python3

import os
import requests
from datetime import datetime
import json

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 语音合成API
voice_synthesis_url = 'https://open.bigmodel.cn/api/paas/v4/audio/speech'

# 语音识别API
voice_recognition_url = 'https://open.bigmodel.cn/api/paas/v4/audio/transcriptions'

# 语音合成参数
synthesis_params = {
    "model": "glm-5.3",
    "text": "发票需要在七个工作日内申请",
    "speed": 1.0,
    "volume": 1.0,
    "voice": "default"
}

# 发送语音合成请求
response = requests.post(voice_synthesis_url, headers={'Authorization': f'Bearer {api_key}'}, json=synthesis_params)
if response.status_code != 200:
    print('语音合成失败')
    exit(1)

# 保存音频文件
audio_file_path = 'invoice.mp3'
with open(audio_file_path, 'wb') as f:
    f.write(response.content)

# 语音识别参数
recognition_params = {
    "model": "glm-5.3",
    "audio": "invoice.mp3"
}

# 发送语音识别请求
response = requests.post(voice_recognition_url, headers={'Authorization': f'Bearer {api_key}'}, json=recognition_params)
if response.status_code != 200:
    print('语音识别失败')
    exit(1)

# 打印识别结果
transcription = response.json()['choices'][0]['message']['content']
print('识别结果：', transcription)

# 比对原文和识别结果
original_text = '发票需要在七个工作日内申请'
if original_text == transcription:
    print('链路打通，测试成功')
else:
    print('链路未打通，测试失败')
