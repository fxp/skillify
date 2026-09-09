#!/usr/bin/env python3
"""
语音链路验证脚本
1. 使用智谱AI语音合成将文本转为音频
2. 立即使用语音识别将音频转回文本
3. 比对原文与识别结果
"""

import os
import requests
import json

# 配置
API_BASE = "https://open.bigmodel.cn/api"
API_KEY = os.environ.get("ZHIPUAI_API_KEY")

# 测试文本
TEST_TEXT = "发票需要在七个工作日内申请"

def test_tts_asr_roundtrip():
    """测试语音链路是否打通"""
    if not API_KEY:
        print("❌ 错误：未设置 ZHIPUAI_API_KEY 环境变量")
        return False

    print("🚀 开始语音链路验证测试...")
    print(f"📝 原文：{TEST_TEXT}")
    print()

    # Step 1: 语音合成
    print("🎙️ Step 1: 调用语音合成接口...")
    try:
        tts_resp = requests.post(
            f"{API_BASE}/paas/v4/audio/speech",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": "glm-tts",
                "input": TEST_TEXT,
                "voice": "tongtong",
                "response_format": "wav"  # 必须指定为 wav 格式才能被 ASR 识别
            }
        )
        tts_resp.raise_for_status()
        print("✅ 语音合成请求成功")

        # 保存音频文件
        audio_file = "test_audio.wav"
        with open(audio_file, "wb") as f:
            f.write(tts_resp.content)
        print(f"🎵 音频文件已保存到: {audio_file}")

    except requests.exceptions.RequestException as e:
        print(f"❌ 语音合成失败: {e}")
        return False

    print()

    # Step 2: 语音识别
    print("🎧 Step 2: 调用语音识别接口...")
    try:
        with open(audio_file, "rb") as f:
            asr_resp = requests.post(
                f"{API_BASE}/paas/v4/audio/transcriptions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                data={"model": "glm-asr-2512"},
                files={"file": ("test_audio.wav", f, "audio/wav")}
            )
        asr_resp.raise_for_status()
        asr_result = asr_resp.json()
        print("✅ 语音识别请求成功")

        # 提取识别文本
        recognized_text = asr_result.get("text", "")
        print(f"📝 识别结果：{recognized_text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ 语音识别失败: {e}")
        return False

    print()

    # Step 3: 比对结果
    print("🔍 Step 3: 比对结果...")
    print(f"📝 原文：{TEST_TEXT}")
    print(f"📝 识别：{recognized_text}")

    # 简单比对（忽略标点和空格）
    original_clean = TEST_TEXT.replace("，", "").replace("。", "").replace("！", "").replace("？", "").replace(" ", "")
    recognized_clean = recognized_text.replace("，", "").replace("。", "").replace("！", "").replace("？", "").replace(" ", "")

    if original_clean == recognized_clean:
        print("✅ 链路验证成功！原文与识别结果匹配")
        return True
    else:
        print("❌ 链路验证失败！原文与识别结果不匹配")
        print(f"   原文清理后：{original_clean}")
        print(f"   识别清理后：{recognized_clean}")
        return False

if __name__ == "__main__":
    success = test_tts_asr_roundtrip()
    if success:
        print("\n🎉 语音链路完全打通！")
    else:
        print("\n💥 语音链路存在问题，请检查上述错误信息")