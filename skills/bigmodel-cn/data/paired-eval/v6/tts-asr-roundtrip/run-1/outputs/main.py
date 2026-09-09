#!/usr/bin/env python3
"""
语音链路验证脚本
使用智谱AI的TTS合成语音，再用ASR转写回文字，验证链路是否通畅
"""
import os
import requests
import json

def check_api_key():
    """检查API Key是否存在"""
    api_key = os.environ.get('ZHIPUAI_API_KEY')
    if not api_key:
        raise ValueError("环境变量 ZHIPUAI_API_KEY 未设置")
    return api_key

def synthesize_speech(api_key, text, output_file="output.wav"):
    """
    使用TTS合成语音
    :param api_key: API密钥
    :param text: 要合成的文本
    :param output_file: 输出文件名
    :return: 成功返回True，失败返回False
    """
    print(f"🎤 开始语音合成: '{text}'")

    url = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()

        with open(output_file, "wb") as f:
            f.write(resp.content)

        print(f"✅ 语音合成成功，保存到 {output_file}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ 语音合成失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        return False

def transcribe_audio(api_key, audio_file):
    """
    使用ASR转写音频
    :param api_key: API密钥
    :param audio_file: 音频文件路径
    :return: 成功返回转写结果，失败返回None
    """
    print(f"🎧 开始语音识别: {audio_file}")

    url = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    try:
        with open(audio_file, "rb") as f:
            files = {"file": (audio_file, f, "audio/wav")}
            data = {"model": "glm-asr-2512"}

            resp = requests.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()

            result = resp.json()
            transcribed_text = result.get("text", "")

            print(f"✅ 语音识别成功，转写结果: '{transcribed_text}'")
            return transcribed_text

    except requests.exceptions.RequestException as e:
        print(f"❌ 语音识别失败: {e}")
        if e.response:
            print(f"响应内容: {e.response.text}")
        return None

def main():
    # 原始文本
    original_text = "发票需要在七个工作日内申请"

    print("=" * 50)
    print("🚀 开始语音链路验证")
    print("=" * 50)

    try:
        # 检查API Key
        api_key = check_api_key()
        print("✅ API Key 已设置")

        # 合成语音
        audio_file = "temp_audio.wav"
        if not synthesize_speech(api_key, original_text, audio_file):
            print("\n❌ 链路验证失败: 语音合成环节失败")
            return

        # 语音识别
        transcribed_text = transcribe_audio(api_key, audio_file)
        if transcribed_text is None:
            print("\n❌ 链路验证失败: 语音识别环节失败")
            return

        # 比对结果
        print("\n" + "=" * 50)
        print("📊 验证结果")
        print("=" * 50)
        print(f"原始文本: '{original_text}'")
        print(f"转写文本: '{transcribed_text}'")

        # 去除标点和空格进行比较
        original_clean = original_text.strip()
        transcribed_clean = transcribed_text.strip()

        if original_clean == transcribed_clean:
            print("\n🎉 链路验证成功！语音合成和识别都正常工作")
            return True
        else:
            print(f"\n⚠️  链路验证失败: 内容不匹配")
            print(f"差异: 原文有{len(original_text)}字符，转写有{len(transcribed_text)}字符")
            return False

    except Exception as e:
        print(f"\n❌ 链路验证失败: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)