#!/usr/bin/env python3
"""智谱开放平台语音链路冒烟测试（上线前检查）。

链路：GLM-TTS 合成「发票需要在七个工作日内申请」→ 落盘 WAV →
      GLM-ASR-2512 把这份 WAV 转写回文字 → 与原文比对，给出链路是否打通的结论。

任何一步失败都会明确报出卡在哪一步、接口返回了什么，不会只报「已生成音频」。

用法：
    export ZHIPUAI_API_KEY=<你的 Key>
    python3 main.py

退出码：0 = 链路打通；1 = 链路不通（stderr 写明卡在哪一步）。
"""

import difflib
import os
import sys
import unicodedata
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
TTS_URL = f"{BASE_URL}/paas/v4/audio/speech"
ASR_URL = f"{BASE_URL}/paas/v4/audio/transcriptions"

TTS_MODEL = "glm-tts"       # 语音合成模型，接口规定固定值
ASR_MODEL = "glm-asr-2512"  # 语音识别模型，接口规定固定值
VOICE = "tongtong"          # 系统音色「彤彤」

EXPECTED_TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = Path(__file__).resolve().parent / "tts_asr_roundtrip.wav"
TIMEOUT = (10, 120)  # (连接超时, 读取超时)，秒


class SmokeTestError(RuntimeError):
    """冒烟测试失败，message 写明卡在第几步、失败原因。"""


def load_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise SmokeTestError(
            "第 0 步 读取鉴权失败：环境变量 ZHIPUAI_API_KEY 未设置或为空，"
            "请先 export ZHIPUAI_API_KEY=<你的 Key> 再运行。"
        )
    return key


def extract_api_error(resp: requests.Response) -> str:
    """把接口错误响应拼成可读字符串。

    兼容两种形态：{"error": {"code", "message"}}（音频接口文档写明）和
    code/message 平铺在顶层；body 不是 JSON 时给出原始片段。
    """
    try:
        body = resp.json()
    except ValueError:
        snippet = (resp.text or resp.content.hex())[:300]
        return f"HTTP {resp.status_code}，非 JSON 响应：{snippet}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return f"HTTP {resp.status_code}，错误码 {err.get('code')}，{err.get('message')}"
        if "code" in body or "message" in body:
            return f"HTTP {resp.status_code}，错误码 {body.get('code')}，{body.get('message')}"
    return f"HTTP {resp.status_code}，响应体：{str(body)[:300]}"


def synthesize(api_key: str, text: str) -> bytes:
    """第 1 步：GLM-TTS 合成，返回 WAV 二进制。成功响应是音频不是 JSON。"""
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": text,
                "voice": VOICE,
                "response_format": "wav",  # 非流式才支持 wav，流式只有 pcm
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SmokeTestError(
            f"第 1 步 TTS 语音合成失败：请求未能完成（网络错误或超时）：{exc}"
        ) from exc

    if resp.status_code != 200:
        raise SmokeTestError(f"第 1 步 TTS 语音合成失败：{extract_api_error(resp)}")

    audio = resp.content
    # 校验确实是 WAV（RIFF....WAVE 魔数），防止把 JSON 错误体当成音频落盘，
    # 那样第 2 步才会炸，报错位置就串了。
    if not (len(audio) > 44 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"):
        if audio[:1] == b"{":
            raise SmokeTestError(
                f"第 1 步 TTS 语音合成失败：接口返回 JSON 而非音频（{extract_api_error(resp)}）"
            )
        raise SmokeTestError(
            f"第 1 步 TTS 语音合成失败：返回内容不是有效的 WAV 音频"
            f"（收到 {len(audio)} 字节，开头 {audio[:16].hex()}）"
        )
    return audio


def transcribe(api_key: str, wav_bytes: bytes) -> str:
    """第 2 步：上传 WAV 给 GLM-ASR-2512，返回转写文本。"""
    try:
        resp = requests.post(
            ASR_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": ASR_MODEL, "stream": "false"},
            files={"file": (AUDIO_PATH.name, wav_bytes, "audio/wav")},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SmokeTestError(
            f"第 2 步 ASR 语音识别失败：请求未能完成（网络错误或超时）：{exc}"
        ) from exc

    if resp.status_code != 200:
        raise SmokeTestError(f"第 2 步 ASR 语音识别失败：{extract_api_error(resp)}")

    try:
        body = resp.json()
    except ValueError as exc:
        raise SmokeTestError(
            f"第 2 步 ASR 语音识别失败：响应不是 JSON（开头 {resp.content[:64]!r}）"
        ) from exc

    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        # HTTP 200 但 body 带 error 的情况也要拦住
        raise SmokeTestError(f"第 2 步 ASR 语音识别失败：{extract_api_error(resp)}")

    text = body.get("text") if isinstance(body, dict) else None
    if not text or not str(text).strip():
        raise SmokeTestError(
            f"第 2 步 ASR 语音识别失败：转写结果为空，完整响应：{str(body)[:300]}"
        )
    return str(text).strip()


def normalize(text: str) -> str:
    """比对前归一化：全角转半角、阿拉伯数字转汉字、去标点和空白。

    ASR 的正常抖动主要就是标点（原文无句号、转写带句号）和数字写法
    （「七个」可能写成「7个」），这些不该判成链路故障。
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans("0123456789", "零一二三四五六七八九"))
    return "".join(
        ch
        for ch in text
        if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def compare(expected: str, actual: str) -> None:
    """第 3 步：转写与原文比对，打印结论；差异过大抛 SmokeTestError。"""
    norm_expected = normalize(expected)
    norm_actual = normalize(actual)
    matcher = difflib.SequenceMatcher(None, norm_expected, norm_actual)
    ratio = matcher.ratio()

    print(f"      原文（归一化后）：{norm_expected}")
    print(f"      转写（归一化后）：{norm_actual}")
    print(f"      字符相似度：{ratio:.0%}")

    if norm_expected == norm_actual:
        print("      比对结论：转写与原文完全一致。")
        return
    if ratio >= 0.8:
        diffs = "、".join(
            f"「{norm_expected[i1:i2] or '∅'}」→「{norm_actual[j1:j2] or '∅'}」"
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        )
        print(
            f"      比对结论：基本一致（差异 {diffs}），属 ASR 正常转写抖动，"
            "链路判定为通。"
        )
        return
    raise SmokeTestError(
        f"第 3 步 结果比对失败：转写与原文差异过大（相似度 {ratio:.0%}，低于 80% 阈值）。"
        f"转写：「{actual}」 vs 原文：「{expected}」"
    )


def main() -> int:
    print("=" * 56)
    print("智谱语音链路冒烟测试：TTS 合成 → 本地落盘 → ASR 转写 → 比对")
    print("=" * 56)

    try:
        api_key = load_api_key()

        print(f"\n[1/3] 语音合成（GLM-TTS，音色 {VOICE}）：「{EXPECTED_TEXT}」")
        audio = synthesize(api_key, EXPECTED_TEXT)
        AUDIO_PATH.write_bytes(audio)
        print(f"      音频已保存：{AUDIO_PATH}（{len(audio)} 字节，WAV）")

        print(f"\n[2/3] 语音识别（GLM-ASR-2512）：上传 {AUDIO_PATH.name}")
        transcript = transcribe(api_key, audio)
        print(f"      转写结果：「{transcript}」")

        print("\n[3/3] 与原文比对")
        compare(EXPECTED_TEXT, transcript)
    except SmokeTestError as exc:
        print(f"\n❌ 冒烟测试未通过，链路不通：{exc}", file=sys.stderr)
        return 1

    print(
        "\n✅ 冒烟测试通过：TTS 合成、本地落盘、ASR 转写、内容比对全部成功，"
        "语音链路已打通。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
