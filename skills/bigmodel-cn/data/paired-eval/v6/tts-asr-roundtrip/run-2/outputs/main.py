#!/usr/bin/env python3
"""
语音链路验证脚本
1. 使用智谱语音合成（GLM-TTS）将文本转为音频
2. 立即使用语音识别（GLM-ASR-2512）将音频转回文字
3. 比对结果，验证链路是否通畅
"""

import os
import requests
import json
import time
import tempfile

# 从环境变量读取 API Key
API_KEY = os.getenv("ZHIPUAI_API_KEY")
if not API_KEY:
    print("错误：请设置环境变量 ZHIPUAI_API_KEY")
    exit(1)

# API 基础 URL
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 要合成的文本
ORIGINAL_TEXT = "发票需要在七个工作日内申请"

def text_to_speech(text, output_path):
    """使用 GLM-TTS 将文本合成为音频"""
    print(f"🎤 正在合成音频: '{text}'")

    url = f"{BASE_URL}/audio/speech"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav",
        "speed": 1.0,
        "volume": 1.0
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        # 保存音频文件
        with open(output_path, "wb") as f:
            f.write(response.content)

        print(f"✅ 音频已保存到: {output_path}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ 语音合成失败: {e}")
        if e.response:
            print(f"错误详情: {e.response.text}")
        return False

def speech_to_text(audio_path):
    """使用 GLM-ASR-2512 将音频转写为文字"""
    print(f"🎧 正在识别音频: {audio_path}")

    url = f"{BASE_URL}/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with open(audio_path, "rb") as f:
            files = {"file": ("audio.wav", f, "audio/wav")}
            data = {"model": "glm-asr-2512"}

            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()

            result = response.json()
            recognized_text = result.get("text", "")

            print(f"✅ 识别完成: '{recognized_text}'")
            return recognized_text

    except requests.exceptions.RequestException as e:
        print(f"❌ 语音识别失败: {e}")
        if e.response:
            print(f"错误详情: {e.response.text}")
        return None

def compare_texts(original, recognized):
    """比对原文和识别结果"""
    print("\n📊 比对结果:")
    print(f"原文:   '{original}'")
    print(f"识别:   '{recognized}'")
    print(f"长度相同: {len(original) == len(recognized)}")

    # 计算相似度
    similarity = sum(1 for a, b in zip(original, recognized) if a == b) / max(len(original), len(recognized))
    print(f"字符相似度: {similarity:.2%}")

    if original == recognized:
        print("✅ 完全匹配！语音链路通畅！")
        return True
    elif similarity > 0.9:
        print("⚠️  高度匹配，可能有微小差异")
        return True
    else:
        print("❌ 匹配度过低，语音链路存在问题")
        return False

def main():
    print("🔊 开始语音链路验证...")
    print("=" * 50)

    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        audio_path = temp_audio.name

    try:
        # 步骤1: 语音合成
        if not text_to_speech(ORIGINAL_TEXT, audio_path):
            return False

        # 步骤2: 语音识别
        recognized_text = speech_to_text(audio_path)
        if recognized_text is None:
            return False

        # 步骤3: 结果比对
        return compare_texts(ORIGINAL_TEXT, recognized_text)

    finally:
        # 清理临时文件
        if os.path.exists(audio_path):
            os.unlink(audio_path)
            print(f"\n🧹 已清理临时文件: {audio_path}")

if __name__ == "__main__":
    success = main()

    print("\n" + "=" * 50)
    if success:
        print("🎉 语音链路验证通过！")
    else:
        print("💥 语音链路验证失败！")
    print("=" * 50)

    exit(0 if success else 1)