#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本转语音脚本 —— 智谱 GLM-TTS (bigmodel.cn)

只用标准库 requests 直接调用智谱开放平台的 HTTP 接口，把一段文本合成为
语音并保存为 .wav 文件。声音选用一个偏温柔、亲和的女声。

使用前准备：
    1. pip install requests
    2. 在 bigmodel.cn 控制台申请 API Key
    3. export ZHIPU_API_KEY="你的key"       （脚本不会把 key 硬编码在代码里）

用法示例：
    python tts.py "你好，欢迎使用智谱 GLM-TTS 文本转语音服务。"
    python tts.py "你好" -o hello.wav -v tongtong

注意：
    - 接口地址、请求字段名（model / input / voice / response_format）参照
      智谱开放平台 audio/speech 系列接口的通用风格（与业界主流 TTS REST 接口
      基本一致）。由于本次任务未联网核对最新官方文档，字段名如有变化，
      请以 bigmodel.cn 官方文档为准，按需微调 API_URL / MODEL / VOICE。
    - 脚本对两种常见的返回形式都做了兼容：
        a) 接口直接返回二进制音频（Content-Type 为 audio/* 或
           application/octet-stream）；
        b) 接口返回 JSON，音频内容以 base64 字符串放在 data/audio 字段里。
"""

import argparse
import base64
import json
import os
import sys

import requests

# ---------------------------------------------------------------------------
# 基本配置
# ---------------------------------------------------------------------------

# 智谱开放平台 TTS（语音合成）接口地址
API_URL = "https://open.bigmodel.cn/api/paas/v4/audio/speech"

# GLM-TTS 模型名称
DEFAULT_MODEL = "glm-tts"

# 音色：选用一个温柔、亲和的女声。
# "tongtong"（童童）是智谱语音示例中常见的默认女声，音色柔和自然，
# 比较符合“温柔女声”的需求；如果账号下的可用音色列表不同，
# 可以在控制台的语音合成 Demo 里试听后，把下面这个值换成实际的音色 ID。
DEFAULT_VOICE = "tongtong"

DEFAULT_TIMEOUT = 60  # 秒


def text_to_speech(
    text: str,
    output_path: str = "output.wav",
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """调用智谱 GLM-TTS 接口，把 text 合成语音并保存为 wav 文件。

    Args:
        text: 要合成的文本内容。
        output_path: 输出 wav 文件路径。
        voice: 音色名称，默认使用温柔女声。
        model: GLM-TTS 模型名。
        api_key: 智谱 API Key；不传则从环境变量 ZHIPU_API_KEY 读取。
        timeout: 请求超时时间（秒）。

    Returns:
        实际写入的 wav 文件路径。
    """
    if not text or not text.strip():
        raise ValueError("待合成的文本不能为空")

    api_key = api_key or os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未找到 API Key，请先设置环境变量 ZHIPU_API_KEY，"
            "例如：export ZHIPU_API_KEY='你的key'"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"请求智谱 GLM-TTS 接口失败：{exc}") from exc

    if resp.status_code != 200:
        # 尽量把接口返回的错误信息透出来，方便排查（比如 key 无效、余额不足等）。
        detail = resp.text
        try:
            detail = json.dumps(resp.json(), ensure_ascii=False)
        except ValueError:
            pass
        raise RuntimeError(
            f"接口返回错误，状态码 {resp.status_code}：{detail}"
        )

    content_type = resp.headers.get("Content-Type", "")

    if content_type.startswith("audio/") or "octet-stream" in content_type:
        # 接口直接返回二进制音频数据
        audio_bytes = resp.content
    else:
        # 接口返回 JSON，音频以 base64 编码放在某个字段里
        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"无法解析响应内容（既不是音频也不是合法 JSON）：{resp.text[:500]}"
            ) from exc

        b64_audio = (
            data.get("data")
            or data.get("audio")
            or data.get("audio_content")
            or (data.get("choices") or [{}])[0].get("audio", {}).get("data")
        )
        if not b64_audio:
            raise RuntimeError(f"未能从响应 JSON 中解析出音频数据：{data}")

        audio_bytes = base64.b64decode(b64_audio)

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    print(f"[OK] 语音已保存到: {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用智谱 GLM-TTS 把文本合成为 wav 语音文件（温柔女声）"
    )
    parser.add_argument(
        "text",
        nargs="?",
        default="你好，欢迎使用智谱 GLM-TTS 文本转语音服务。",
        help="要合成的文本内容",
    )
    parser.add_argument(
        "-o", "--output",
        default="output.wav",
        help="输出 wav 文件路径，默认 output.wav",
    )
    parser.add_argument(
        "-v", "--voice",
        default=DEFAULT_VOICE,
        help=f"音色名称，默认 '{DEFAULT_VOICE}'（温柔女声）",
    )
    parser.add_argument(
        "-m", "--model",
        default=DEFAULT_MODEL,
        help=f"GLM-TTS 模型名，默认 '{DEFAULT_MODEL}'",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        text_to_speech(
            text=args.text,
            output_path=args.output,
            voice=args.voice,
            model=args.model,
        )
    except Exception as exc:  # noqa: BLE001 - 顶层脚本，统一兜底报错
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
