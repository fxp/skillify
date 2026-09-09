#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱语音链路冒烟测试（上线前检查）。

链路：文本 --GLM-TTS--> wav 音频（落盘） --GLM-ASR-2512--> 转写文本，再与原文比对。

用法：
    export ZHIPUAI_API_KEY=<标准 API Key>
    python3 main.py

判定：TTS 返回合法 WAV 且落盘 + ASR 转写出非空文本 + 与原文基本一致 => 链路通；
任何一步失败都会明确报出卡在哪一步、原因是什么，并以非零退出码结束。
"""

import difflib
import json
import os
import re
import sys
import wave
from pathlib import Path

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = f"{API_BASE}/audio/speech"
ASR_URL = f"{API_BASE}/audio/transcriptions"

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = Path(__file__).resolve().parent / "tts_output.wav"

TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"  # 系统音色「彤彤」
SIMILARITY_FLOOR = 0.6  # 归一化相似度低于此值视为转写异常


def fail(step, reason):
    print(f"\n[失败] {step}")
    print(f"       原因：{reason}")
    print("\n===== 冒烟测试结论：❌ 语音链路未打通（卡在上述步骤） =====")
    sys.exit(1)


def describe_error(resp):
    """把平台的 JSON 错误体（error.code/message 或 code/msg）压成一行可读信息。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应非 JSON：{resp.content[:200]!r}"
    if not isinstance(body, dict):
        return f"HTTP {resp.status_code}，响应：{str(body)[:200]}"
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    code = err.get("code", "?")
    message = err.get("message") or err.get("msg") or str(body)[:200]
    detail = f"HTTP {resp.status_code}，错误码 {code}：{message}"
    if str(code) == "1113":
        detail += (
            "。提示：1113 未必是余额不足——若你用的是 GLM Coding Plan（编程套餐）Key，"
            "它打不了标准端点 /api/paas/v4，且语音能力不在套餐内，请换成标准 API Key 再试"
        )
    return detail


def synthesize(api_key):
    print(f"[2/5] TTS 合成（POST /audio/speech，模型 {TTS_MODEL}，音色 {VOICE}）...")
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": ORIGINAL_TEXT,
                "voice": VOICE,
                # 关键：不传时默认返回裸 PCM，而 ASR 只接受 wav/mp3，给 PCM 改后缀没有用
                "response_format": "wav",
            },
            timeout=(10, 120),
        )
    except requests.RequestException as exc:
        fail("第 2 步 · TTS 合成", f"请求未完成（网络层异常）：{exc!r}")

    if resp.status_code != 200:
        fail("第 2 步 · TTS 合成", describe_error(resp))
    if "json" in resp.headers.get("Content-Type", "").lower():
        fail("第 2 步 · TTS 合成", f"HTTP 200 但返回的是 JSON 而非音频：{describe_error(resp)}")

    audio = resp.content
    if not audio:
        fail("第 2 步 · TTS 合成", "响应体为空，没有拿到任何音频字节")
    # 冒烟要点：校验容器格式本身（magic bytes），而不是只看文件后缀
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        fail(
            "第 2 步 · TTS 合成",
            "音频不是合法 WAV 容器（首部 magic 异常），疑似拿到了裸 PCM"
            "（TTS 默认 response_format=pcm，需显式传 wav 让 ASR 能读）",
        )
    if len(audio) < 1024:
        fail("第 2 步 · TTS 合成", f"音频仅 {len(audio)} 字节，大概率是空音频")

    AUDIO_PATH.write_bytes(audio)
    print(f"      已保存 {len(audio)} 字节 → {AUDIO_PATH}")


def check_wav():
    print("[3/5] 校验音频文件 ...")
    try:
        with wave.open(str(AUDIO_PATH), "rb") as w:
            rate = w.getframerate()
            duration = w.getnframes() / rate if rate else 0.0
            print(f"      WAV 合法：{rate} Hz，{w.getnchannels()} 声道，时长 {duration:.2f} 秒")
    except (wave.Error, EOFError) as exc:
        # magic 校验已通过，标准库解析失败仅提示，最终能不能用交给 ASR 判定
        print(f"      提示：标准库 wave 无法解析该文件（{exc}），继续交给 ASR")
        return
    if duration > 30:
        fail("第 3 步 · 音频校验", f"时长 {duration:.1f} 秒超过 ASR 单次 30 秒上限，需分段调用")


def transcribe(api_key):
    print(f"[4/5] ASR 转写（POST /audio/transcriptions，模型 {ASR_MODEL}）...")
    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (AUDIO_PATH.name, f, "audio/wav")},
                timeout=(10, 120),
            )
    except requests.RequestException as exc:
        fail("第 4 步 · ASR 转写", f"请求未完成（网络层异常）：{exc!r}")

    if resp.status_code != 200:
        fail("第 4 步 · ASR 转写", describe_error(resp))
    try:
        body = resp.json()
    except ValueError:
        fail("第 4 步 · ASR 转写", f"响应非 JSON：{resp.content[:300]!r}")

    text = (body.get("text") or "").strip()
    if not text:
        fail(
            "第 4 步 · ASR 转写",
            "接口返回 200 但没有转写文本，完整响应："
            + json.dumps(body, ensure_ascii=False),
        )
    return text


def normalize(s):
    """去掉标点/空白并统一小写，只留文字本体再比对。"""
    return re.sub(r"[^\w一-鿿]", "", s).lower()


def compare(asr_text):
    print("[5/5] 与原文比对 ...")
    print(f"      原文：{ORIGINAL_TEXT}")
    print(f"      转写：{asr_text}")
    a, b = normalize(ORIGINAL_TEXT), normalize(asr_text)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    print(f"      归一化后原文：{a}")
    print(f"      归一化后转写：{b}")
    print(f"      相似度：{ratio:.0%}")
    if a == b:
        print("\n===== 冒烟测试结论：✅ 语音链路已打通，转写与原文完全一致 =====")
        return
    if ratio >= SIMILARITY_FLOOR:
        print("\n===== 冒烟测试结论：✅ 语音链路已打通（TTS 合成、落盘、ASR 转写均正常） =====")
        print(f"      注意：转写与原文不完全一致（相似度 {ratio:.0%}），多为标点或「七/7」类写法差异，上线前建议人工确认。")
        return
    fail(
        "第 5 步 · 文本比对",
        f"转写内容与原文差异过大（相似度 {ratio:.0%}），疑似合成或识别环节有问题，"
        f"请人工试听音频 {AUDIO_PATH} 排查",
    )


def main():
    print("===== 智谱语音链路冒烟测试（TTS → 落盘 → ASR → 比对） =====")
    print("[1/5] 读取环境变量 ZHIPUAI_API_KEY ...")
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("第 1 步 · 环境变量", "ZHIPUAI_API_KEY 未设置或为空，请先 export ZHIPUAI_API_KEY=<你的标准 API Key>")
    print("      OK")

    synthesize(api_key)
    check_wav()
    transcribed = transcribe(api_key)
    compare(transcribed)


if __name__ == "__main__":
    main()
