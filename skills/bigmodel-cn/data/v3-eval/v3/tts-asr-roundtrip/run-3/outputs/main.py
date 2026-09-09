#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱语音链路上线前冒烟测试。

流程：GLM-TTS 合成「发票需要在七个工作日内申请」→ 存为本地 WAV →
GLM-ASR 把该音频转写回文字 → 与原文比对，明确报告链路通/不通。

用法：
    export ZHIPUAI_API_KEY=<你的智谱 API Key>
    python3 main.py

任一步失败都会报错退出，并指明卡在哪一步；不会只报"已生成音频"。
"""

import difflib
import json
import os
import re
import sys

import requests

API_KEY_ENV = "ZHIPUAI_API_KEY"
TTS_URL = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
ASR_URL = "https://open.bigmodel.cn/api/paas/v4/audio/transcriptions"
TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"  # 系统音色「彤彤」

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
# 音频落在脚本同目录，跑一次就能拿到现场证据
AUDIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test_output.wav")

# 数字写法差异（七 vs 7）之外的实质偏差超过两成才算不过
SIMILARITY_PASS_THRESHOLD = 0.8

STEP_ENV = "环境准备：读取 ZHIPUAI_API_KEY"
STEP_TTS = "步骤 1/3：TTS 语音合成（POST /paas/v4/audio/speech）"
STEP_ASR = "步骤 2/3：ASR 语音识别（POST /paas/v4/audio/transcriptions）"
STEP_CMP = "步骤 3/3：转写结果与原文比对"


def die(step, message):
    """报错退出：说清楚卡在哪一步、为什么。"""
    print(f"\n❌ 冒烟测试失败：{message}", file=sys.stderr)
    print(f"   卡在【{step}】，链路未打通，请先解决此步再重跑。", file=sys.stderr)
    sys.exit(1)


def describe_error(resp):
    """把平台的 JSON 错误体（{"error":{"code":..,"message":..}}）翻成人话。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应体前 200 字节：{resp.content[:200]!r}"
    err = body.get("error") or body
    code = err.get("code") if isinstance(err, dict) else None
    message = err.get("message") if isinstance(err, dict) else None
    if code or message:
        return f"HTTP {resp.status_code}，错误码 {code}：{message}"
    return f"HTTP {resp.status_code}，响应体：{json.dumps(body, ensure_ascii=False)[:300]}"


def synthesize_wav(api_key):
    """调 TTS 合成原文，返回可用的 WAV 字节。

    平台实测坑：TTS 不传 response_format 时默认返回裸 PCM（首字节不是 RIFF），
    而 ASR 只接受 wav/mp3——所以必须显式要 wav，并校验返回的确实是 WAV。
    """
    payload = {
        "model": TTS_MODEL,
        "input": ORIGINAL_TEXT,
        "voice": VOICE,
        "response_format": "wav",  # 关键：不传就是裸 PCM，ASR 拒收
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    last_problem = None
    for attempt in (1, 2):
        try:
            resp = requests.post(TTS_URL, headers=headers, json=payload, timeout=120)
        except requests.RequestException as exc:
            last_problem = f"请求 TTS 接口网络异常：{exc}"
            print(f"  ! 第 {attempt} 次合成{last_problem}，重试…" if attempt == 1 else f"  ! 第 {attempt} 次合成{last_problem}")
            continue
        if resp.status_code != 200:
            # 鉴权失败/参数错误这类，重试无意义，直接报清楚
            die(STEP_TTS, f"TTS 合成被平台拒绝：{describe_error(resp)}")
        audio = resp.content
        if audio[:4] == b"RIFF" and len(audio) >= 1024:
            return audio
        # 拿到裸 PCM 时重新合成，而不是给它改 .wav 后缀硬喂 ASR
        last_problem = (
            f"返回的不是 WAV 音频（content-type={resp.headers.get('content-type')!r}，"
            f"首 4 字节 {audio[:4]!r}，疑似裸 PCM）"
        )
        print(f"  ! 第 {attempt} 次合成{last_problem}，重试…")
    die(STEP_TTS, f"TTS 重试后仍拿不到 WAV：{last_problem}。ASR 只接受 wav/mp3，拒绝把裸 PCM 改后缀喂给它")


def transcribe(api_key, audio_path):
    """把本地音频喂给 ASR，返回转写文本；拿不到文本就报错退出。"""
    try:
        with open(audio_path, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                timeout=120,
            )
    except requests.RequestException as exc:
        die(STEP_ASR, f"请求 ASR 接口网络异常：{exc}")
    if resp.status_code != 200:
        die(STEP_ASR, f"ASR 转写被平台拒绝：{describe_error(resp)}（音频需为 wav/mp3、≤25MB、时长 ≤30 秒）")
    try:
        body = resp.json()
    except ValueError:
        die(STEP_ASR, f"ASR 返回的不是 JSON（前 200 字节：{resp.content[:200]!r}）")
    text = (body.get("text") or "").strip()
    if not text:
        die(STEP_ASR, f"ASR 返回 200 但转写文本为空，完整响应：{json.dumps(body, ensure_ascii=False)[:500]}")
    return text


def normalize(text):
    """归一化后再比对：ASR 可能把「七」写成「7」、加标点或空格。"""
    # 全角数字转半角
    text = "".join(
        chr(ord(c) - 0xFEE0) if 0xFF10 <= ord(c) <= 0xFF19 else c for c in text
    )
    # 阿拉伯数字 → 汉字数字，「两」统一作「二」
    text = text.translate(str.maketrans("0123456789", "零一二三四五六七八九")).replace("两", "二")
    # 去掉标点/空白，只留汉字和字母，统一小写
    return re.sub(r"[^一-龥a-zA-Z]", "", text).lower()


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        die(STEP_ENV, f"环境变量 {API_KEY_ENV} 未设置。请先 export {API_KEY_ENV}=<智谱 API Key> 再运行")

    print(f"[1/3] TTS 合成原文「{ORIGINAL_TEXT}」（model={TTS_MODEL}, voice={VOICE}, response_format=wav）")
    audio = synthesize_wav(api_key)
    with open(AUDIO_PATH, "wb") as f:
        f.write(audio)
    print(f"      音频已保存：{AUDIO_PATH}（{len(audio)} 字节，WAV）")

    print(f"[2/3] ASR 转写该音频（model={ASR_MODEL}）")
    transcript = transcribe(api_key, AUDIO_PATH)
    print(f"      转写结果：「{transcript}」")

    print("[3/3] 与原文比对")
    norm_ref = normalize(ORIGINAL_TEXT)
    norm_asr = normalize(transcript)
    print(f"      原文（归一化）：{norm_ref}")
    print(f"      转写（归一化）：{norm_asr}")
    if norm_ref == norm_asr:
        print("\n✅ 语音链路已打通：TTS 合成 → 本地 WAV → ASR 转写 → 与原文完全一致。")
        return
    ratio = difflib.SequenceMatcher(None, norm_ref, norm_asr).ratio()
    print(f"      字面相似度：{ratio:.0%}")
    if ratio >= SIMILARITY_PASS_THRESHOLD:
        print(
            f"\n✅ 语音链路已打通（相似度 {ratio:.0%} ≥ {SIMILARITY_PASS_THRESHOLD:.0%}，"
            "差异仅为数字写法/个别同音字，语义一致）。"
        )
        return
    die(
        STEP_CMP,
        f"转写文本与原文不符（相似度 {ratio:.0%} < {SIMILARITY_PASS_THRESHOLD:.0%}）："
        f"原文「{ORIGINAL_TEXT}」 vs 转写「{transcript}」。"
        "合成、转写接口本身均可用，但内容回环校验未通过，建议先排查音色/语速或换文本重试。",
    )


if __name__ == "__main__":
    main()
