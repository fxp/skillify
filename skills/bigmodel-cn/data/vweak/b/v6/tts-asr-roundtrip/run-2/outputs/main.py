#!/usr/bin/env python3
import os
import requests

# 获取API Key
api_key = os.environ['ZHIPUAI_API_KEY']

# 语音合成
def synthesize_speech(text, api_key):
    url = 'https://open.bigmodel.cn/api/paas/v4/audio/speech'
    headers = {'Authorization': f'Bearer {api_key}'}
    data = {'text': text}
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# 语音识别
def recognize_speech(audio_file, api_key):
    url = 'https://open.bigmodel.cn/api/paas/v4/audio/transcriptions'
    headers = {'Authorization': f'Bearer {api_key}'}
    files = {'file': ('audio.mp3', open(audio_file, 'rb'), 'audio/mp3')}
    response = requests.post(url, headers=headers, files=files)
    return response.json()['results'][0]['result_text']

# 主函数
def main):
    # 合成语音
    synthesized_audio = synthesize_speech('发票需要在七个工作日内申请', api_key)
    audio_file = 'output_audio.mp3'
    with open(audio_file, 'wb') as f:
        f.write(synthesized_audio)
    # 识别语音
    recognized_text = recognize_speech(audio_file, api_key)
    # 打印识别结果
    print('识别结果：', recognized_text)
    # 比对原文
    original_text = '发票需要在七个工作日内申请'
    if recognized_text == original_text:
        print('链路通，识别结果与原文一致。')
    else:
        print('链路不通，识别结果与原文不一致。')

if __name__ == '__main__':
    main()