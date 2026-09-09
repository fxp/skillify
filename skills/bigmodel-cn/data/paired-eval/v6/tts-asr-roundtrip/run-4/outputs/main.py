#!/usr/bin/env python3
"""
语音链路测试脚本
测试流程：
1. 使用智谱TTS将文本「发票需要在七个工作日内申请」合成音频
2. 立即使用ASR将音频转写回文字
3. 比对结果并输出链路状态
"""

import os
import requests
import json
from pathlib import Path

def test_tts_asr_chain():
    """测试完整的TTS-ASR链路"""

    # 配置
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False

    base_url = "https://open.bigmodel.cn/api"
    headers = {"Authorization": f"Bearer {api_key}"}

    # 测试文本
    test_text = "发票需要在七个工作日内申请"
    audio_file = "test_audio.wav"

    print("=" * 50)
    print("🎤 开始测试语音链路")
    print("=" * 50)
    print(f"📝 测试文本：{test_text}")

    # 第一步：TTS语音合成
    print("\n🔊 步骤1：语音合成 (TTS)")
    tts_endpoint = f"{base_url}/paas/v4/audio/speech"

    tts_payload = {
        "model": "glm-tts",
        "input": test_text,
        "voice": "tongtong",
        "response_format": "wav",  # 必须用wav格式，ASR不支持pcm
        "speed": 1.0,
        "volume": 1.0
    }

    try:
        print("  正在调用TTS接口...")
        tts_response = requests.post(
            tts_endpoint,
            headers=headers,
            json=tts_payload
        )

        if tts_response.status_code != 200:
            print(f"  ❌ TTS接口调用失败: {tts_response.status_code}")
            print(f"  错误详情: {tts_response.text}")
            return False

        print(f"  ✅ TTS接口调用成功，音频大小: {len(tts_response.content)} 字节")

        # 保存音频文件
        with open(audio_file, "wb") as f:
            f.write(tts_response.content)
        print(f"  📁 音频已保存至: {audio_file}")

    except requests.exceptions.RequestException as e:
        print(f"  ❌ TTS请求异常: {str(e)}")
        return False
    except Exception as e:
        print(f"  ❌ TTS未知错误: {str(e)}")
        return False

    # 第二步：ASR语音识别
    print("\n🎧 步骤2：语音识别 (ASR)")
    asr_endpoint = f"{base_url}/paas/v4/audio/transcriptions"

    try:
        # 检查音频文件是否存在
        if not Path(audio_file).exists():
            print(f"  ❌ 音频文件不存在: {audio_file}")
            return False

        with open(audio_file, "rb") as f:
            print("  正在调用ASR接口...")
            asr_response = requests.post(
                asr_endpoint,
                headers=headers,
                data={"model": "glm-asr-2512"},
                files={"file": (audio_file, f, "audio/wav")}
            )

        if asr_response.status_code != 200:
            print(f"  ❌ ASR接口调用失败: {asr_response.status_code}")
            print(f"  错误详情: {asr_response.text}")
            return False

        asr_result = asr_response.json()
        transcribed_text = asr_result.get("text", "")
        print(f"  ✅ ASR接口调用成功，识别文本: {transcribed_text}")

    except requests.exceptions.RequestException as e:
        print(f"  ❌ ASR请求异常: {str(e)}")
        return False
    except Exception as e:
        print(f"  ❌ ASR未知错误: {str(e)}")
        return False

    # 第三步：结果比对
    print("\n🔍 步骤3：结果比对")
    print(f"  原文:  {test_text}")
    print(f"  识别:  {transcribed_text}")

    # 去除标点符号和空格进行比对（ASR可能不会保留标点）
    original_clean = test_text.replace("，", "").replace("。", "").replace("、", "").replace(" ", "")
    transcribed_clean = transcribed_text.replace("，", "").replace("。", "").replace("、", "").replace(" ", "")

    match = original_clean == transcribed_clean

    if match:
        print("\n🎉 链路测试结果：成功！")
        print("✅ 语音合成 → 语音识别链路完全打通")
        print("✅ 识别结果与原文一致")
        return True
    else:
        print("\n❌ 链路测试结果：失败！")
        print("❌ 识别结果与原文不匹配")
        print(f"❌ 原文处理后: {original_clean}")
        print(f"❌ 识别处理后: {transcribed_clean}")
        return False

def main():
    """主函数"""
    print("语音链路冒烟测试")
    print("测试流程：文本 → TTS合成 → ASR识别 → 结果比对")

    success = test_tts_asr_chain()

    if success:
        print("\n" + "=" * 50)
        print("🚀 链路状态：已打通，可以上线使用")
        print("=" * 50)
        return 0
    else:
        print("\n" + "=" * 50)
        print("🚨 链路状态：未打通，需要修复")
        print("=" * 50)
        return 1

if __name__ == "__main__":
    exit(main())