#!/usr/bin/env python3
import os
import requests
import json

# 获取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 语音合成API
url_tts = 'https://open.bigmodel.cn/api/paas/v4/audio/speech'

# 语音识别API
url_asr = 'https://open.bigmodel.cn/api/paas/v4/audio/transcriptions'

# 语音合成文本
text_to_speak = '发票需要在七个工作日内申请'

# 发起语音合成请求
response_tts = requests.post(url_tts, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}, json={
    'model': 'glm-5.3',
    'text': text_to_speak
})

# 检查语音合成响应
if response_tts.status_code != 200:
    raise Exception('语音合成请求失败')

# 保存音频文件
audio_file_path = 'output_audio.mp3'
with open(audio_file_path, 'wb') as f:
    f.write(response_tts.content)

# 语音识别请求
response_asr = requests.post(url_asr, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}, json={
    'model': 'glm-5.3',
    'audio': open(audio_file_path, 'rb')
})

# 检查语音识别响应
if response_asr.status_code != 200:
    raise Exception('语音识别请求失败')

# 读取识别结果
asr_result = response_asr.json()['result']['text']

# 打印识别结果
print('语音识别结果：', asr_result)

# 比较识别结果与原文
if asr_result.lower() == text_to_speak.lower():
    print('语音链路打通，识别结果与原文一致。')
else:
    print('语音链路未打通，识别结果与原文不一致。')
