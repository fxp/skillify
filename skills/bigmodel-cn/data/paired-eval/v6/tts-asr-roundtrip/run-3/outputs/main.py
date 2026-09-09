#!/usr/bin/env python3
"""
语音链路验证脚本
使用智谱AI的语音合成和语音验证TTS-ASR链路是否通畅
"""

import os
import requests
import time

# 配置
API_KEY = os.environ.get('ZHIPUAI_API_KEY')
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 测试文本
TEST_TEXT = "发票需要在七个工作日内申请"

def check_api_key():
    """检查API Key是否设置"""
    if not API_KEY:
        raise ValueError("未设置 ZHIPUAI_API_KEY 环境变量")
    print("✓ API Key 已设置")

def text_to_speech(text, output_file="output.wav"):
    """文本转语音"""
    print(f"\n1. 正在合成语音: {text}")

    url = f"{BASE_URL}/audio/speech"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": "tongtong",
        "response_format": "wav",
        "speed": 1.0,
        "volume": 1.0
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        # 保存音频文件
        with open(output_file, "wb") as f:
            f.write(response.content)
        print(f"✓ 音频已保存到: {output_file}")

        # 检查文件大小
        file_size = os.path.getsize(output_file)
        print(f"✓ 音频文件大小: {file_size} 字节")

        if file_size == 0:
            raise ValueError("生成的音频文件为空")

        return output_file

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "401" in error_msg:
            raise ValueError("API Key 无效或已过期")
        elif "429" in error_msg:
            raise ValueError("请求频率过高，请稍后重试")
        elif "500" in error_msg or "503" in error_msg:
            raise ValueError("服务器错误，请稍后重试")
        else:
            raise ValueError(f"语音合成失败: {error_msg}")

def speech_to_text(audio_file):
    """语音转文字"""
    print(f"\n2. 正在识别音频: {audio_file}")

    url = f"{BASE_URL}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        with open(audio_file, "rb") as f:
            files = {"file": (audio_file, f, "audio/wav")}
            data = {"model": "glm-asr-2512"}

            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            transcribed_text = result.get("text", "")

            print(f"✓ 转写结果: {transcribed_text}")
            print(f"✓ 请求ID: {result.get('id', 'N/A')}")

            return transcribed_text

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if "401" in error_msg:
            raise ValueError("API Key 无效或已过期")
        elif "429" in error_msg:
            raise ValueError("请求频率过高，请稍后重试")
        elif "400" in error_msg:
            # 可能是音频格式不支持
            if "format" in error_msg.lower():
                raise ValueError("音频格式不支持，请确保使用 wav 格式")
            else:
                raise ValueError("请求参数错误")
        else:
            raise ValueError(f"语音识别失败: {error_msg}")

def compare_texts(original, transcribed):
    """比较原文和转写结果"""
    print(f"\n3. 比较结果:")
    print(f"   原文: {original}")
    print(f"   转写: {transcribed}")

    # 去除标点符号和空格进行比较（ASR 可能不输出标点）
    original_clean = original.strip()
    transcribed_clean = transcribed.strip()

    if original_clean == transcribed_clean:
        print("✓ 链路通畅！原文与转写结果一致")
        return True
    else:
        # 计算相似度
        similarity = len(set(original_clean) & set(transcribed_clean)) / len(set(original_clean) | set(transcribed_clean))
        print(f"⚠ 链路部分通畅，但存在差异（相似度: {similarity:.2%}）")

        # 显示具体差异
        if original_clean != transcribed_clean:
            print("差异分析:")
            print(f"   原文长度: {len(original_clean)} 字符")
            print(f"   转写长度: {len(transcribed_clean)} 字符")

            # 检查是否只是标点符号差异
            import re
            original_no_punct = re.sub(r'[^\w一-鿿]', '', original_clean)
            transcribed_no_punct = re.sub(r'[^\w一-鿿]', '', transcribed_clean)

            if original_no_punct == transcribed_no_punct:
                print("   差异仅来自标点符号，语义内容一致")
                return True
            else:
                print("   存在语义差异，请检查音频质量和网络状况")
                return False

def main():
    """主函数"""
    print("=" * 50)
    print("语音链路验证开始")
    print("=" * 50)

    try:
        # 1. 检查API Key
        check_api_key()

        # 2. 文本转语音
        audio_file = text_to_speech(TEST_TEXT)

        # 3. 语音转文字
        transcribed_text = speech_to_text(audio_file)

        # 4. 比较结果
        is_success = compare_texts(TEST_TEXT, transcribed_text)

        # 5. 清理临时文件
        if os.path.exists(audio_file):
            os.remove(audio_file)
            print(f"\n✓ 已清理临时文件: {audio_file}")

        # 6. 最终结果
        print("\n" + "=" * 50)
        if is_success:
            print("🎉 语音链路验证成功！TTS-ASR 链路通畅")
            print("=" * 50)
        else:
            print("❌ 语音链路验证失败！请检查以下环节：")
            print("   - API Key 是否有效")
            print("   - 网络连接是否正常")
            print("   - 音频文件是否正确生成")
            print("   - 是否超出音频大小限制（25MB）或时长限制（30秒）")
            print("=" * 50)

        return is_success

    except Exception as e:
        print(f"\n❌ 链路验证过程中发生错误: {str(e)}")

        # 如果有生成音频文件，保留它用于调试
        if 'audio_file' in locals() and os.path.exists(audio_file):
            print(f"⚠ 保留音频文件用于调试: {audio_file}")

        print("=" * 50)
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)