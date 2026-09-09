#!/usr/bin/env python3
"""
语音链路验证脚本
测试：TTS → ASR → 验证
"""

import os
import requests
import time

# 配置
BASE_URL = "https://open.bigmodel.cn/api"
API_KEY = os.getenv("ZHIPUAI_API_KEY")
TEXT_TO_SYNTHESIZE = "发票需要在七个工作日内申请"

# 输出文件路径
OUTPUT_WAV_FILE = "output.wav"
LOG_FILE = "test_log.txt"

def test_tts():
    """测试语音合成"""
    print("=" * 50)
    print("第一步：语音合成（TTS）")
    print("=" * 50)

    if not API_KEY:
        print("❌ 错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False

    try:
        # TTS 请求
        tts_url = f"{BASE_URL}/paas/v4/audio/speech"
        tts_payload = {
            "model": "glm-tts",
            "input": TEXT_TO_SYNTHESIZE,
            "voice": "tongtong",
            "response_format": "wav"
        }

        tts_response = requests.post(
            tts_url,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=tts_payload
        )

        if tts_response.status_code != 200:
            print(f"❌ TTS 请求失败，状态码：{tts_response.status_code}")
            print(f"响应内容：{tts_response.text}")
            return False

        # 检查响应类型
        content_type = tts_response.headers.get('content-type', '')
        if 'audio' not in content_type:
            print(f"❌ 错误：响应不是音频格式，Content-Type: {content_type}")
            return False

        # 保存音频文件
        with open(OUTPUT_WAV_FILE, "wb") as f:
            f.write(tts_response.content)

        file_size = os.path.getsize(OUTPUT_WAV_FILE)
        print(f"✅ TTS 成功，音频已保存为 {OUTPUT_WAV_FILE}")
        print(f"   文件大小：{file_size} 字节")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ TTS 请求异常：{str(e)}")
        return False
    except Exception as e:
        print(f"❌ TTS 未知错误：{str(e)}")
        return False

def test_asr():
    """测试语音识别"""
    print("\n" + "=" * 50)
    print("第二步：语音识别（ASR）")
    print("=" * 50)

    if not os.path.exists(OUTPUT_WAV_FILE):
        print("❌ 错误：音频文件不存在，无法进行 ASR")
        return False, None

    try:
        # ASR 请求
        asr_url = f"{BASE_URL}/paas/v4/audio/transcriptions"

        with open(OUTPUT_WAV_FILE, "rb") as f:
            files = {"file": ("test.wav", f, "audio/wav")}
            data = {"model": "glm-asr-2512"}

            asr_response = requests.post(
                asr_url,
                headers={"Authorization": f"Bearer {API_KEY}"},
                files=files,
                data=data
            )

        if asr_response.status_code != 200:
            print(f"❌ ASR 请求失败，状态码：{asr_response.status_code}")
            print(f"响应内容：{asr_response.text}")
            return False, None

        asr_result = asr_response.json()
        recognized_text = asr_result.get("text", "")

        print(f"✅ ASR 成功，识别结果：")
        print(f"   「{recognized_text}」")
        return True, recognized_text

    except requests.exceptions.RequestException as e:
        print(f"❌ ASR 请求异常：{str(e)}")
        return False, None
    except Exception as e:
        print(f"❌ ASR 未知错误：{str(e)}")
        return False, None

def verify_results(original_text, recognized_text):
    """验证结果"""
    print("\n" + "=" * 50)
    print("第三步：结果验证")
    print("=" * 50)

    print(f"原文：{original_text}")
    print(f"识别：{recognized_text}")

    # 去除空格和标点进行比较（ASR 可能不输出标点）
    original_clean = original_text.replace(" ", "")
    recognized_clean = recognized_text.replace(" ", "")

    if original_clean == recognized_clean:
        print("\n🎉 链路验证成功！语音转写完全匹配原文")
        return True
    else:
        print("\n⚠️  链路验证失败，转写结果与原文不匹配")
        # 提供详细分析
        if len(recognized_clean) < len(original_clean):
            print("   可能原因：漏字或识别不完整")
        elif len(recognized_clean) > len(original_clean):
            print("   可能原因：多字或识别错误")
        else:
            print("   可能原因：字音相似但识别错误")

        # 显示逐字符对比
        print("\n逐字符对比（空格已去除）：")
        print("原文:", " ".join(list(original_clean)))
        print("识别:", " ".join(list(recognized_clean)))
        print("差异:", " ".join("✓" if a == b else "✗" for a, b in zip(original_clean, recognized_clean)))

        return False

def cleanup():
    """清理生成的文件"""
    if os.path.exists(OUTPUT_WAV_FILE):
        os.remove(OUTPUT_WAV_FILE)
        print(f"\n🧹 已清理临时文件：{OUTPUT_WAV_FILE}")

def main():
    """主函数"""
    print("🚀 开始语音链路验证测试")
    print(f"测试文本：「{TEXT_TO_SYNTHESIZE}」")
    print(f"API Key: {'已设置' if API_KEY else '未设置'}")

    # 记录开始时间
    start_time = time.time()

    try:
        # 步骤1：TTS
        tts_success = test_tts()
        if not tts_success:
            print("\n❌ 语音合成失败，链路中断")
            return

        # 步骤2：ASR
        asr_success, recognized_text = test_asr()
        if not asr_success:
            print("\n❌ 语音识别失败，链路中断")
            return

        # 步骤3：验证结果
        if recognized_text is not None:
            verification_success = verify_results(TEXT_TO_SYNTHESIZE, recognized_text)

            # 计算耗时
            end_time = time.time()
            duration = end_time - start_time

            print("\n" + "=" * 50)
            print("测试总结")
            print("=" * 50)
            print(f"总耗时：{duration:.2f} 秒")

            if verification_success:
                print("\n✅ 整体结论：语音链路完全正常，可以上线！")
            else:
                print("\n❌ 整体结论：语音链路存在问题，需要排查后再上线")
        else:
            print("\n❌ 无法获取识别结果，链路测试失败")

    finally:
        # 清理
        cleanup()

if __name__ == "__main__":
    main()