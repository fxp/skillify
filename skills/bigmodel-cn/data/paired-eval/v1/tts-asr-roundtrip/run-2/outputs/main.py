#!/usr/bin/env python3
"""
语音链路验证脚本
使用智谱AI的语音合成和识别接口验证语音链路是否打通
"""

import os
import requests
import time

# API 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.getenv("ZHIPUAI_API_KEY")

# 待合成的文本
ORIGINAL_TEXT = "发票需要在七个工作日内申请"

# 音频文件路径
AUDIO_FILE = "generated_audio.wav"

def print_step(title, content=""):
    """打印步骤信息"""
    print(f"\n{'='*50}")
    print(f"步骤: {title}")
    if content:
        print(f"内容: {content}")
    print('='*50)

def check_api_key():
    """检查 API Key 是否存在"""
    if not API_KEY:
        raise ValueError("❌ 错误: 未找到 ZHIPUAI_API_KEY 环境变量！\n"
                      "请运行: export ZHIPUAI_API_KEY='your-api-key'")
    print("✅ API Key 已配置")

def text_to_speech(text, output_file):
    """文本转语音 - GLM-TTS"""
    print_step("语音合成", f"文本: {text}")

    url = f"{BASE_URL}/paas/v4/audio/speech"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav",  # 必须使用 wav 格式才能被 ASR 识别
        "speed": 1.0,
        "volume": 1.0,
        "watermark_enabled": True
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        # 保存音频文件
        with open(output_file, "wb") as f:
            f.write(response.content)

        print(f"✅ 音频合成成功，已保存至: {output_file}")
        print(f"   文件大小: {len(response.content)} 字节")

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ 音频合成失败: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   响应状态码: {e.response.status_code}")
            print(f"   响应内容: {e.response.text}")
        return False

def speech_to_text(audio_file):
    """语音转文字 - GLM-ASR"""
    print_step("语音识别", f"音频文件: {audio_file}")

    url = f"{BASE_URL}/paas/v4/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    with open(audio_file, "rb") as f:
        files = {
            "file": (os.path.basename(audio_file), f, "audio/wav")
        }
        data = {
            "model": "glm-asr-2512"
        }

        try:
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()

            result = response.json()
            recognized_text = result.get("text", "")

            print(f"✅ 语音识别成功")
            print(f"   识别结果: {recognized_text}")

            return recognized_text

        except requests.exceptions.RequestException as e:
            print(f"❌ 语音识别失败: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"   响应状态码: {e.response.status_code}")
                print(f"   响应内容: {e.response.text}")
            return None

def compare_texts(original, recognized):
    """比对原文和识别结果"""
    print_step("结果比对")

    print(f"原文:  '{original}'")
    print(f"识别:  '{recognized}'")

    # 清理文本进行比对（去除可能的空格差异）
    original_clean = original.strip()
    recognized_clean = recognized.strip() if recognized else ""

    if original_clean == recognized_clean:
        print("\n🎉 链路验证成功！")
        print("✅ 语音合成和识别工作正常")
        print("✅ 识别结果与原文完全一致")
        return True
    else:
        print("\n❌ 链路验证失败！")
        print("❌ 识别结果与原文不一致")

        # 计算差异
        diff_pos = []
        min_len = min(len(original_clean), len(recognized_clean))

        for i in range(min_len):
            if original_clean[i] != recognized_clean[i]:
                diff_pos.append(i)

        if diff_pos:
            print(f"   首个差异位置: 第 {diff_pos[0] + 1} 个字符")
            print(f"   原文差异: '{original_clean[diff_pos[0]:diff_pos[0]+10] if diff_pos else ''}'")
            print(f"   识别差异: '{recognized_clean[diff_pos[0]:diff_pos[0]+10] if diff_pos else ''}'")

        return False

def main():
    """主流程"""
    print("🚀 开始语音链路验证...")
    print(f"待验证文本: '{ORIGINAL_TEXT}'")

    # 检查 API Key
    try:
        check_api_key()
    except ValueError as e:
        print(str(e))
        return False

    success = True

    # 步骤1: 文本转语音
    if not text_to_speech(ORIGINAL_TEXT, AUDIO_FILE):
        success = False
        return False

    # 步骤2: 语音转文字
    recognized_text = speech_to_text(AUDIO_FILE)
    if not recognized_text:
        success = False
        return False

    # 步骤3: 比对结果
    compare_success = compare_texts(ORIGINAL_TEXT, recognized_text)
    success = success and compare_success

    # 清理临时文件
    try:
        os.remove(AUDIO_FILE)
        print(f"\n🧹 已清理临时文件: {AUDIO_FILE}")
    except OSError:
        pass

    # 输出最终结果
    print("\n" + "="*50)
    if success:
        print("🎯 最终结果: 语音链路验证成功！")
        print("   所有步骤执行正常，TTS 和 ASR 接口工作正常")
    else:
        print("💥 最终结果: 语音链路验证失败！")
        print("   请检查上述错误信息，确认卡在哪个步骤")
    print("="*50)

    return success

if __name__ == "__main__":
    # 设置请求超时
    requests.Session().timeout = 30

    # 执行主流程
    exit_code = 0 if main() else 1
    exit(exit_code)