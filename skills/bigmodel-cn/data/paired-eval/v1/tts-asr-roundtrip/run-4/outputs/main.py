#!/usr/bin/env python3
"""
语音链路验证脚本
1. 使用智谱TTS将文本合成音频
2. 使用智谱ASR将音频转写回文字
3. 对比原文和转写结果
"""

import os
import requests
from pathlib import Path

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api"

# 测试文本
ORIGINAL_TEXT = "发票需要在七个工作日内申请"

# 文件路径
AUDIO_FILE = "test_speech.wav"


def check_api_key():
    """检查API Key是否已设置"""
    if not API_KEY:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        print("请在终端中执行：export ZHIPUAI_API_KEY='your_api_key'")
        return False
    return True


def text_to_speech(text, audio_file):
    """
    使用智谱TTS将文本合成音频
    """
    print(f"🎤 正在合成音频：{text}")

    url = f"{BASE_URL}/paas/v4/audio/speech"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav"  # 必须使用wav格式，否则ASR无法识别
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        # 保存音频文件
        with open(audio_file, "wb") as f:
            f.write(response.content)

        print(f"✅ 音频已保存至：{audio_file}")
        print(f"📊 音频文件大小：{os.path.getsize(audio_file)} 字节")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ TTS请求失败：{e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误码：{e.response.status_code}")
            print(f"错误信息：{e.response.text}")
        return False


def speech_to_text(audio_file):
    """
    使用智谱ASR将音频转写为文字
    """
    print(f"🎧 正在识别音频：{audio_file}")

    url = f"{BASE_URL}/paas/v4/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with open(audio_file, "rb") as f:
            files = {
                "file": (audio_file, f, "audio/wav")
            }
            data = {
                "model": "glm-asr-2512"
            }

            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            recognized_text = result.get("text", "")

            print(f"✅ 识别成功，转写结果：{recognized_text}")
            return recognized_text

    except requests.exceptions.RequestException as e:
        print(f"❌ ASR请求失败：{e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误码：{e.response.status_code}")
            print(f"错误信息：{e.response.text}")
        return None
    except Exception as e:
        print(f"❌ 处理音频文件失败：{e}")
        return None


def compare_texts(original, recognized):
    """
    对比原文和转写结果
    """
    print("\n" + "="*50)
    print("📋 对比结果：")
    print(f"📝 原文：{original}")
    print(f"🔍 转写：{recognized}")

    # 标准化文本：去除标点和空格进行比较
    original_clean = original.strip()
    recognized_clean = recognized.strip() if recognized else ""

    if recognized_clean:
        if original_clean == recognized_clean:
            print("\n🎉 链路验证成功！语音合成和识别完全匹配！")
            return True
        else:
            print("\n⚠️  链路基本打通，但内容有差异：")
            print("   - 可能原因：标点符号差异、语气词、识别误差")
            print("   - 建议：检查音频清晰度和背景噪音")
            return True
    else:
        print("\n❌ 链路验证失败！未能识别出文字内容")
        return False


def cleanup():
    """清理生成的音频文件"""
    if os.path.exists(AUDIO_FILE):
        os.remove(AUDIO_FILE)
        print(f"\n🧹 已清理临时文件：{AUDIO_FILE}")


def main():
    """主函数"""
    print("="*60)
    print("🚀 语音链路验证开始")
    print("="*60)

    # 检查API Key
    if not check_api_key():
        return

    # 清理旧文件
    if os.path.exists(AUDIO_FILE):
        os.remove(AUDIO_FILE)

    success = False

    try:
        # 第一步：TTS语音合成
        tts_success = text_to_speech(ORIGINAL_TEXT, AUDIO_FILE)
        if not tts_success:
            print("\n❌ 语音合成失败，无法继续进行识别")
            return

        # 第二步：ASR语音识别
        recognized_text = speech_to_text(AUDIO_FILE)
        if recognized_text is None:
            print("\n❌ 语音识别失败，链路不通")
            return

        # 第三步：对比结果
        success = compare_texts(ORIGINAL_TEXT, recognized_text)

    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 发生未知错误：{e}")
    finally:
        # 清理
        cleanup()

        # 输出最终结论
        print("\n" + "="*60)
        if success:
            print("🎯 总结论：语音链路已打通！")
        else:
            print("💥 总结论：语音链路存在问题，需要检查！")
        print("="*60)


if __name__ == "__main__":
    main()