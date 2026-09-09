# main.py

import os
import requests

def main():
    # 读取API Key
    api_key = os.environ['ZHIPUAI_API_KEY']

    # 语音合成
    synthesis_url = 'https://open.bigmodel.cn/api/paas/v4/audio/speech'
    synthesis_data = {
        "text": "发票需要在七个工作日内申请",
        "model": "glm-tts",
        "volume": 1.0,
        "speed": 1.0
    }
    synthesis_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    synthesis_response = requests.post(synthesis_url, headers=synthesis_headers, json=synthesis_data)
    synthesis_response.raise_for_status()
    audio_data = synthesis_response.json()

    # 保存音频文件
    with open('invoice_audio.mp3', 'wb') as f:
        f.write(audio_data['audio'])

    # 语音识别
    recognition_url = 'https://open.bigmodel.cn/api/paas/v4/audio/transcriptions'
    recognition_data = {
        "audio": "",  # 音频数据将通过上传文件发送
        "model": "glm-asr-2512"
    }
    recognition_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "multipart/form-data"
    }
    with open('invoice_audio.mp3', 'rb') as f:
        recognition_data['audio'] = f.read()
    recognition_response = requests.post(recognition_url, headers=recognition_headers, files={
        'file': ('invoice_audio.mp3', f, 'audio/mp3')
    })
    recognition_response.raise_for_status()
    recognition_result = recognition_response.json()

    # 输出识别结果并比对
    print('Recognition result:', recognition_result['transcription'])
    print('Original text:', "发票需要在七个工作日内申请")

if __name__ == '__main__':
    main()