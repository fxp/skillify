#!/usr/bin/env python3
"""
文本转语音脚本 —— 使用智谱开放平台（bigmodel.cn）的 GLM-TTS 模型。

直接用标准库 requests 调用 HTTP 接口：
    POST https://open.bigmodel.cn/api/paas/v4/audio/speech

音色选择：tongtong（彤彤）—— 智谱 GLM-TTS 的系统音色之一，是一个温柔、柔和的
女声，也是官方文档示例中使用的默认音色，适合旁白、语音助手等需要亲和力的场景。

用法：
    export ZHIPUAI_API_KEY="你的真实 API Key"
    python tts.py "你好，欢迎使用智谱开放平台。" -o speech.wav

也可以不传文本参数，脚本会使用内置的示例文本。
"""

from __future__ import annotations

import argparse
import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
TTS_ENDPOINT = f"{BASE_URL}/paas/v4/audio/speech"

# GLM-TTS 系统音色：tongtong（彤彤）是一个温柔的女声，语气柔和自然，
# 是官方文档里的默认/示例音色。其他可选系统音色包括 chuichui（锤锤）、
# xiaochen（小陈）、jam、kazi、douji、luodo，也可以传自己复刻出的音色名。
VOICE_GENTLE_FEMALE = "tongtong"

DEFAULT_TEXT = "你好，欢迎使用智谱开放平台。这是一段用于测试的语音合成文本。"


def synthesize_speech(
    text: str,
    output_path: str,
    api_key: str,
    voice: str = VOICE_GENTLE_FEMALE,
    speed: float = 1.0,
    volume: float = 1.0,
) -> None:
    """调用 GLM-TTS 接口，把文本合成为语音并保存为 wav 文件。"""

    if not text:
        raise ValueError("待合成文本不能为空")
    if len(text) > 1024:
        raise ValueError("待合成文本超过 1024 字符限制，请先分段")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "glm-tts",
        "input": text,
        "voice": voice,
        "speed": speed,
        "volume": volume,
        # 非流式场景下才能拿到 wav，流式模式只支持 pcm。
        "response_format": "wav",
        "stream": False,
    }

    resp = requests.post(TTS_ENDPOINT, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    # 注意：TTS 接口成功时返回的是音频二进制（wav），不是 JSON，
    # 所以这里直接用 resp.content 写文件，不能调用 resp.json()。
    with open(output_path, "wb") as f:
        f.write(resp.content)

    print(f"语音已保存到: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用智谱 GLM-TTS 把文本合成为 wav 语音文件")
    parser.add_argument(
        "text",
        nargs="?",
        default=DEFAULT_TEXT,
        help="要合成的文本（默认使用内置示例文本）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="speech.wav",
        help="输出 wav 文件路径（默认: speech.wav）",
    )
    parser.add_argument(
        "--voice",
        default=VOICE_GENTLE_FEMALE,
        help=f"音色名称（默认: {VOICE_GENTLE_FEMALE}，一个温柔的女声）",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="语速，范围 [0.5, 2]（默认: 1.0）",
    )
    parser.add_argument(
        "--volume",
        type=float,
        default=1.0,
        help="音量，范围 (0, 10]（默认: 1.0）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print(
            "错误: 请先设置环境变量 ZHIPUAI_API_KEY（在 "
            "https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）。",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        synthesize_speech(
            text=args.text,
            output_path=args.output,
            api_key=api_key,
            voice=args.voice,
            speed=args.speed,
            volume=args.volume,
        )
    except requests.HTTPError as e:
        print(f"请求失败: {e}\n响应内容: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"网络请求出错: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
