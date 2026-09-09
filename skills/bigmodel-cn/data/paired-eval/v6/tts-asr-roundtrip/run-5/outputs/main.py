#!/usr/bin/env python3
"""
语音链路验证脚本
1. 使用智谱TTS合成文本「发票需要在七个工作日内申请」
2. 使用智谱ASR识别生成的音频
3. 比对结果，验证链路是否打通
"""

import os
import requests
import json

# 配置
API_KEY = os.environ.get("ZHIPUAI_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 测试文本
ORIGINAL_TEXT = "发票需要在七个工作日内申请"
AUDIO_FILE = "generated_speech.wav"

def check_api_key():
    """检查API Key是否存在"""
    if not API_KEY:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY")
        return False
    return True

def text_to_speech(text, output_file):
    """
    使用智谱TTS将文本转换为语音
    返回: (成功状态, 错误信息)
    """
    print(f"步骤1：使用TTS合成文本: '{text}'")

    headers = {"Authorization": f"Bearer {API_KEY}"}
    data = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav"  # 必须使用wav格式才能被ASR识别
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/audio/speech",
            headers=headers,
            json=data
        )

        if resp.status_code != 200:
            return False, f"TTS请求失败: HTTP {resp.status_code}, {resp.text}"

        # 检查响应内容是否为音频数据
        if not resp.content:
            return False, "TTS响应为空，未返回音频数据"

        # 保存音频文件
        with open(output_file, "wb") as f:
            f.write(resp.content)

        print(f"✓ 音频已生成: {output_file} (大小: {len(resp.content)} 字节)")
        return True, None

    except requests.exceptions.RequestException as e:
        return False, f"TTS请求异常: {str(e)}"
    except Exception as e:
        return False, f"TTS未知错误: {str(e)}"

def speech_to_transcription(audio_file):
    """
    使用智谱ASR将语音转换为文本
    返回: (识别文本, 错误信息)
    """
    print(f"步骤2：使用ASR识别音频文件: {audio_file}")

    headers = {"Authorization": f"Bearer {API_KEY}"}
    data = {"model": "glm-asr-2512"}

    try:
        with open(audio_file, "rb") as f:
            files = {"file": (os.path.basename(audio_file), f, "audio/wav")}
            resp = requests.post(
                f"{BASE_URL}/audio/transcriptions",
                headers=headers,
                data=data,
                files=files
            )

        if resp.status_code != 200:
            return None, f"ASR请求失败: HTTP {resp.status_code}, {resp.text}"

        result = resp.json()

        if "text" not in result:
            return None, f"ASR响应格式异常，缺少text字段: {result}"

        transcribed_text = result["text"]
        print(f"✓ 识别结果: '{transcribed_text}'")
        return transcribed_text, None

    except requests.exceptions.RequestException as e:
        return None, f"ASR请求异常: {str(e)}"
    except json.JSONDecodeError as e:
        return None, f"ASR响应解析失败: {str(e)}"
    except Exception as e:
        return None, f"ASR未知错误: {str(e)}"

def compare_texts(original, transcribed):
    """比对原文和识别结果"""
    print("\n=== 链路验证结果 ===")
    print(f"原文:   '{original}'")
    print(f"识别:   '{transcribed}'")

    # 去除标点符号和空格进行比较
    original_clean = original.strip().replace("，", "").replace("。", "").replace("！", "").replace("？", "")
    transcribed_clean = transcribed.strip().replace("，", "").replace("。", "").replace("！", "").replace("？", "")

    if original_clean == transcribed_clean:
        print("\n✓ 链路验证成功！语音合成和识别正常工作。")
        return True
    else:
        print(f"\n✗ 链路验证失败！识别结果与原文不一致。")
        print(f"差异对比：")
        print(f"  原文长度: {len(original)} 字符")
        print(f"  识别长度: {len(transcribed)} 字符")
        return False

def main():
    """主函数"""
    print("开始语音链路验证...\n")

    # 检查API Key
    if not check_api_key():
        return 1

    # 步骤1: TTS合成
    tts_success, tts_error = text_to_speech(ORIGINAL_TEXT, AUDIO_FILE)
    if not tts_success:
        print(f"\n❌ TTS阶段失败: {tts_error}")
        print("请检查：")
        print("  1. API Key是否正确")
        print("  2. 是否有足够的额度")
        print("  3. 网络连接是否正常")
        return 1

    # 步骤2: ASR识别
    asr_result, asr_error = speech_to_transcription(AUDIO_FILE)
    if asr_result is None:
        print(f"\n❌ ASR阶段失败: {asr_error}")
        print("请检查：")
        print("  1. API Key是否正确")
        print("  2. 是否有足够的额度")
        print("  3. 音频文件是否正确生成（必须是wav格式）")
        print("  4. 音频时长是否超过30秒")
        return 1

    # 步骤3: 比对结果
    success = compare_texts(ORIGINAL_TEXT, asr_result)

    # 清理临时文件
    if os.path.exists(AUDIO_FILE):
        os.remove(AUDIO_FILE)

    return 0 if success else 1

if __name__ == "__main__":
    exit(main())