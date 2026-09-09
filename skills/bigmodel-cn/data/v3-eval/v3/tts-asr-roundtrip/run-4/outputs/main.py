#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱语音链路上线前冒烟测试。

流程：GLM-TTS 合成「发票需要在七个工作日内申请」-> 落盘本地 wav
      -> GLM-ASR 把该音频转写回文字 -> 与原文比对，明确报告链路是否打通。

任何一步失败都会带着步骤名和平台错误码退出（exit 1），不会只说"已生成音频"。

依赖：仅 requests。运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = f"{API_BASE}/audio/speech"
ASR_URL = f"{API_BASE}/audio/transcriptions"
TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"

TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = Path(__file__).resolve().parent / "tts_asr_roundtrip.wav"
REQUEST_TIMEOUT = (10, 120)  # (连接超时, 读取超时)，单位秒


class StepError(RuntimeError):
    """冒烟测试在某一步失败：step 定位环节，detail 说明原因。"""

    def __init__(self, step, detail):
        self.step = step
        self.detail = detail
        super().__init__(f"[{step}] {detail}")


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise StepError(
            "读取 API Key",
            "环境变量 ZHIPUAI_API_KEY 未设置（先 export ZHIPUAI_API_KEY=你的Key 再运行）",
        )
    return key


def describe_api_error(resp):
    """把平台 JSON 错误体（error.code / error.message）拼成可读文本。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应非 JSON：{resp.content[:200]!r}"
    err = body.get("error") or body
    return f"HTTP {resp.status_code}，code={err.get('code')}，message={err.get('message')}"


def synthesize_speech(api_key, text):
    """第 1 步：文本 -> wav 音频字节。

    必须显式传 response_format="wav"：接口默认返回裸 PCM（无 RIFF 头），
    ASR 端点只接受 wav/mp3，给 PCM 改 .wav 后缀是没用的。
    """
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": text,
                "voice": VOICE,
                "response_format": "wav",  # 关键：默认 pcm 无法直接喂给 ASR
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StepError("TTS 语音合成", f"网络请求失败：{exc}") from exc

    if resp.status_code != 200:
        raise StepError("TTS 语音合成", describe_api_error(resp))

    audio = resp.content
    if not audio:
        raise StepError("TTS 语音合成", "HTTP 200 但响应体为空，没有拿到任何音频字节")

    # 防御性校验：平台出错时回 JSON；正常应是二进制 wav（RIFF 头）
    content_type = resp.headers.get("content-type", "")
    if audio[:1] == b"{" or "json" in content_type:
        try:
            err = resp.json().get("error") or resp.json()
            detail = f"code={err.get('code')}，message={err.get('message')}"
        except ValueError:
            detail = repr(audio[:300])
        raise StepError("TTS 语音合成", f"期望音频二进制，却拿到 JSON 错误体：{detail}")
    if audio[:4] != b"RIFF":
        raise StepError(
            "TTS 语音合成",
            f"音频不是合法 wav（首 4 字节应为 b'RIFF'，实际 {audio[:4]!r}，"
            f"content-type={content_type}）——疑似拿到裸 PCM，ASR 只接受 wav/mp3，"
            "请确认 response_format=wav 生效",
        )
    return audio


def transcribe_audio(api_key, audio_path):
    """第 3 步：wav 文件 -> 转写文本（multipart 上传给 ASR，≤25MB / ≤30s）。"""
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (audio_path.name, f, "audio/wav")},
                timeout=REQUEST_TIMEOUT,
            )
    except requests.RequestException as exc:
        raise StepError(
            "ASR 语音识别", f"网络请求失败（音频已生成在 {audio_path}）：{exc}"
        ) from exc

    if resp.status_code != 200:
        raise StepError(
            "ASR 语音识别", f"音频已生成在 {audio_path}；" + describe_api_error(resp)
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise StepError(
            "ASR 语音识别",
            f"响应不是 JSON：{resp.content[:300]!r}（音频文件保留在 {audio_path}）",
        ) from exc

    if isinstance(body, dict) and body.get("error"):
        raise StepError(
            "ASR 语音识别",
            "HTTP 200 但平台返回错误："
            + json.dumps(body["error"], ensure_ascii=False),
        )

    transcribed = (body.get("text") or "").strip() if isinstance(body, dict) else ""
    if not transcribed:
        raise StepError(
            "ASR 语音识别",
            f"HTTP 200 但没有转写出文本，完整响应：{json.dumps(body, ensure_ascii=False)}",
        )
    return transcribed


def normalize(text):
    """比对前归一化：去掉空白和标点（ASR 常在句末加/漏标点）。"""
    return re.sub(r"[^\w]", "", text)


def main():
    print("=" * 62)
    print("智谱语音链路冒烟测试：TTS 合成 -> 本地 wav -> ASR 转写 -> 比对")
    print("=" * 62)

    api_key = get_api_key()
    print("[1/4] API Key：已从环境变量 ZHIPUAI_API_KEY 读取")

    print(f"[2/4] TTS 语音合成：{TEXT!r}")
    print(f"      model={TTS_MODEL}，voice={VOICE}，response_format=wav")
    audio = synthesize_speech(api_key, TEXT)
    AUDIO_PATH.write_bytes(audio)
    print(f"      音频已落盘：{AUDIO_PATH}（{len(audio)} 字节）")

    print(f"[3/4] ASR 语音识别：上传 {AUDIO_PATH.name}，model={ASR_MODEL}")
    transcribed = transcribe_audio(api_key, AUDIO_PATH)
    print(f"      转写结果：{transcribed!r}")

    src, out = normalize(TEXT), normalize(transcribed)
    exact = src == out
    ratio = SequenceMatcher(None, src, out).ratio()
    print("[4/4] 与原文比对：")
    print(f"      原文：{TEXT}")
    print(f"      转写：{transcribed}")
    print(f"      归一化后{'完全一致' if exact else '不一致'}，相似度 {ratio:.0%}")

    print("-" * 62)
    if exact or ratio >= 0.9:
        print("✅ 冒烟测试通过：TTS -> ASR 语音链路已打通，转写内容与原文一致。")
        return 0
    print("❌ 冒烟测试不通过：两个接口均有响应，但转写内容与原文差异过大，")
    print("   需人工核查（见上方原文/转写对照与相似度）。")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StepError as exc:
        print("=" * 62)
        print(f"❌ 冒烟测试失败：链路在【{exc.step}】这一步断了。")
        print(f"   失败原因：{exc.detail}")
        if AUDIO_PATH.exists():
            print(f"   音频文件已保留在 {AUDIO_PATH}，可手动播放/排查。")
        sys.exit(1)
