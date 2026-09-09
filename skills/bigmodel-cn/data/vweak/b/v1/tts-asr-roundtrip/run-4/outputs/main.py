#!/usr/bin/env python3

import os
import requests

# 读取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 语音合成
def synthesize_text_to_audio(text, api_key):
    url = 'https://open.bigmodel.cn/api/paas/v4/audio/speech'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'text': text
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['audio_url']
    else:
        raise Exception('语音合成失败')

# 语音识别
def recognize_audio_to_text(audio_url, api_key):
    url = 'https://open.bigmodel.cn/api/paas/v4/audio/transcriptions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'audio_url': audio_url
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()['text']
    else:
        raise Exception('语音识别失败')

# 主函数
def main):
    text = '发票需要在七个工作日内申请'
    try:
        # 语音合成
        audio_url = synthesize_text_to_audio(text, api_key)
        print('已生成音频')
        # 语音识别
        recognized_text = recognize_audio_to_text(audio_url, api_key)
        print('识别结果:', recognized_text)
        # 比对结果
        if recognized_text == text:
            print('链路打通')
        else:
            print('链路未打通，识别结果与原文不一致')
    except Exception as e:
        print('测试失败:', e)

if __name__ == '__main__':
    main()