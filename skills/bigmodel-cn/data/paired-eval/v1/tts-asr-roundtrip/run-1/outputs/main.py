#!/usr/bin/env python3
"""
语音链路验证脚本
使用智谱AI的语音合成(TTS)生成音频，然后用语音识别(ASR)转写回文字，验证链路是否打通
"""

import os
import requests
import json

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = 'https://open.bigmodel.cn/api'

# 要合成的文本
TEXT_TO_SYNTHESIZE = '发票需要在七个工作日内申请'
OUTPUT_AUDIO_FILE = 'generated_speech.wav'

def test_tts_synthesis():
    """测试语音合成"""
    print("=== 步骤1：语音合成 ===")
    print(f"正在合成文本：{TEXT_TO_SYNTHESIZE}")

    # 检查API Key
    if not API_KEY:
        print("错误：未设置 ZHIPUAI_API_KEY 环境变量")
        return None

    # 请求TTS API
    try:
        response = requests.post(
            f"{BASE_URL}/paas/v4/audio/speech",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": "glm-tts",
                "input": TEXT_TO_SYNTHESIZE,
                "voice": "tongtong",
                "response_format": "wav",  # 必须使用wav格式才能被ASR识别
            },
            timeout=30
        )
        response.raise_for_status()

        # 保存音频文件
        with open(OUTPUT_AUDIO_FILE, 'wb') as f:
            f.write(response.content)
        print(f"音频已保存到：{OUTPUT_AUDIO_FILE}")
        print(f"音频文件大小：{len(response.content)} 字节")
        return OUTPUT_AUDIO_FILE

    except requests.exceptions.RequestException as e:
        print(f"TTS合成失败：{e}")
        if e.response:
            print(f"错误响应：{e.response.text}")
        return None

def test_asr_transcription(audio_file):
    """测试语音识别"""
    print("\n=== 步骤2：语音识别 ===")
    print(f"正在识别音频文件：{audio_file}")

    try:
        # 读取音频文件
        with open(audio_file, 'rb') as f:
            files = {
                'file': (audio_file, f, 'audio/wav'),
                'model': (None, 'glm-asr-2512')
            }

            response = requests.post(
                f"{BASE_URL}/paas/v4/audio/transcriptions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                files=files,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            recognized_text = result.get('text', '')

            print(f"识别结果：{recognized_text}")
            return recognized_text

    except requests.exceptions.RequestException as e:
        print(f"ASR识别失败：{e}")
        if e.response:
            print(f"错误响应：{e.response.text}")
        return None

def compare_texts(original, recognized):
    """比较原文和识别结果"""
    print("\n=== 步骤3：结果比对 ===")
    print(f"原文：{original}")
    print(f"识别：{recognized}")

    # 去除标点符号和空格进行比较
    original_clean = original.replace('，', '').replace('。', '').replace(' ', '')
    recognized_clean = recognized.replace('，', '').replace('。', '').replace(' ', '')

    if original_clean == recognized_clean:
        print("\n✅ 链路验证成功！语音合成和识别正常工作。")
        return True
    else:
        print(f"\n❌ 链路验证失败！")
        print(f"差异：")
        print(f"- 原文长度：{len(original_clean)} 字符")
        print(f"- 识别长度：{len(recognized_clean)} 字符")
        print(f"- 是否匹配：{original_clean == recognized_clean}")
        return False

def main():
    """主函数"""
    print("开始语音链路验证...\n")

    # 步骤1：语音合成
    audio_file = test_tts_synthesis()
    if not audio_file:
        print("\n❌ 语音合成失败，链路验证中断。")
        return False

    # 步骤2：语音识别
    recognized_text = test_asr_transcription(audio_file)
    if not recognized_text:
        print("\n❌ 语音识别失败，链路验证中断。")
        return False

    # 步骤3：比对结果
    success = compare_texts(TEXT_TO_SYNTHESIZE, recognized_text)

    # 清理临时文件
    try:
        os.remove(audio_file)
        print(f"\n已清理临时文件：{audio_file}")
    except:
        pass

    return success

if __name__ == "__main__":
    success = main()
    print(f"\n最终结果：{'✅ 链路完全打通！' if success else '❌ 链路有问题，需要检查！'}")
    exit(0 if success else 1)