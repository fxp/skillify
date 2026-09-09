#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱语音链路冒烟测试（上线前 smoke test）

链路：GLM-TTS 合成「发票需要在七个工作日内申请」→ 落盘 wav
   → GLM-ASR-2512 立刻把该 wav 转写回文字 → 与原文比对，给出链路通/不通的结论。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

退出码：0 = 链路打通；1 = 链路在某一步断掉（错误信息会写明卡在哪一步）。
依赖：仅 requests。
"""

import difflib
import json
import os
import re
import struct
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = API_BASE + "/audio/speech"
ASR_URL = API_BASE + "/audio/transcriptions"

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
VOICE = "tongtong"
AUDIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_output.wav")

# ASR 硬限制：单次请求音频 ≤25MB 且 ≤30 秒
MAX_BYTES = 25 * 1024 * 1024
MAX_SECONDS = 30.0
# 比对判定：归一化后相似度达到该阈值即认为往返一致（容忍个别错字或"七/7"这类写法差异）
SIMILARITY_THRESHOLD = 0.8


def fail(step, message):
    """冒烟测试不允许含糊：明确报出断在哪一步，然后以非零码退出。"""
    print(f"\n❌ 链路未打通：卡在【{step}】")
    print(f"   {message}")
    sys.exit(1)


def extract_error(resp):
    """尽量从错误响应里挖出平台错误码与信息，方便定位（兼容 error 嵌套与顶层两种结构）。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应非 JSON：{resp.text[:300]!r}"
    if isinstance(body.get("error"), dict):
        err = body["error"]
        return f"HTTP {resp.status_code}，错误码 {err.get('code')}：{err.get('message')}"
    if "code" in body or "message" in body:
        return f"HTTP {resp.status_code}，错误码 {body.get('code')}：{body.get('message')}"
    return f"HTTP {resp.status_code}，响应：{json.dumps(body, ensure_ascii=False)[:300]}"


def wav_duration_seconds(path):
    """读 wav 头估算时长，用于送 ASR 前自查 30 秒限制（按 44 字节标准 PCM 头粗算）。"""
    with open(path, "rb") as f:
        header = f.read(44)
    if len(header) < 44 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise ValueError(f"不是合法的 WAV 文件头（前 12 字节：{header[:12]!r}）")
    byte_rate = struct.unpack("<I", header[28:32])[0]  # fmt 块的 byte_rate 字段
    if byte_rate == 0:
        raise ValueError("WAV 头 byte_rate 为 0，无法估算时长")
    return (os.path.getsize(path) - 44) / byte_rate


def synthesize(api_key):
    """调用 GLM-TTS 合成 wav 音频并落盘，返回 (字节数, 时长秒)。"""
    payload = {
        "model": "glm-tts",
        "input": ORIGINAL_TEXT,
        "voice": VOICE,
        # 关键：response_format 不传时平台默认返回裸 PCM（audio/pcm，首 4 字节不是 RIFF），
        # 而 ASR 只收 wav/mp3——改后缀没用，必须显式要 wav。
        "response_format": "wav",
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    resp = None
    content = b""
    for attempt in (1, 2):
        try:
            resp = requests.post(TTS_URL, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            fail("第 1 步 TTS 语音合成", f"网络请求异常：{e!r}")
        if resp.status_code != 200:
            fail("第 1 步 TTS 语音合成", extract_error(resp))
        content = resp.content or b""
        if content[:4] == b"RIFF":
            break
        # HTTP 200 但拿到的不像 wav（比如裸 PCM）：按补救措施带着 wav 参数重试一次
        print(f"⚠️  TTS 返回 200 但内容不是 wav（content-type={resp.headers.get('content-type')}，"
              f"首 4 字节={content[:4]!r}），{'重试一次' if attempt == 1 else '两次都不是 wav，判定失败'}")
    if content[:4] != b"RIFF":
        detail = extract_error(resp) if resp is not None else "无响应"
        fail("第 1 步 TTS 语音合成",
             f"接口未返回 wav 音频（可能返回了裸 PCM 或 JSON 错误）。{detail}")

    with open(AUDIO_PATH, "wb") as f:
        f.write(content)
    size = os.path.getsize(AUDIO_PATH)
    if size == 0:
        fail("第 1 步 TTS 语音合成", "落盘的音频文件为空（0 字节）")
    try:
        duration = wav_duration_seconds(AUDIO_PATH)
    except ValueError:
        duration = float("nan")  # 头解析失败不在这里阻断，第 2 步自查会再报
    return size, duration


def transcribe(api_key):
    """调用 GLM-ASR-2512 转写 AUDIO_PATH，返回转写文本。"""
    size = os.path.getsize(AUDIO_PATH)
    if size > MAX_BYTES:
        fail("第 2 步 ASR 语音识别", f"音频 {size} 字节，超过 ASR 单次 25MB 上限")
    try:
        duration = wav_duration_seconds(AUDIO_PATH)
    except ValueError as e:
        fail("第 2 步 ASR 语音识别", f"音频文件自查失败：{e}")
    if duration > MAX_SECONDS:
        fail("第 2 步 ASR 语音识别", f"音频约 {duration:.1f} 秒，超过 ASR 单次 30 秒上限")

    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": "glm-asr-2512"},
                files={"file": ("audio.wav", f, "audio/wav")},
                timeout=120,
            )
    except requests.RequestException as e:
        fail("第 2 步 ASR 语音识别", f"网络请求异常：{e!r}")
    if resp.status_code != 200:
        hint = ""
        if "格式" in resp.text or "format" in resp.text.lower():
            hint = "（提示：ASR 仅支持 wav/mp3；本脚本已显式请求 wav，请检查文件头是否为 RIFF）"
        fail("第 2 步 ASR 语音识别", extract_error(resp) + hint)
    try:
        body = resp.json()
    except ValueError:
        fail("第 2 步 ASR 语音识别", f"响应不是 JSON：{resp.text[:300]!r}")
    if isinstance(body.get("error"), dict):
        fail("第 2 步 ASR 语音识别",
             f"错误码 {body['error'].get('code')}：{body['error'].get('message')}")
    text = (body.get("text") or "").strip()
    if not text:
        fail("第 2 步 ASR 语音识别",
             "接口返回 200 但转写文本为空，完整响应："
             + json.dumps(body, ensure_ascii=False)[:300])
    return text


_PUNCT_RE = re.compile(r"[\s，。！？、；：·…“”‘’\"'.,!?;:()\[\]（）【】]+")
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def normalize(s):
    """去掉标点和空白、全角数字转半角，只留实质内容再比对。"""
    return _PUNCT_RE.sub("", s or "").translate(_FULLWIDTH_DIGITS)


def compare(original, transcribed):
    """返回 (归一化后是否逐字一致, 相似度 0~1)。"""
    a, b = normalize(original), normalize(transcribed)
    ratio = difflib.SequenceMatcher(None, a, b).ratio() if b else 0.0
    return a == b, ratio


def main():
    try:  # 防止个别终端（如 Windows GBK）打印 emoji 直接崩掉
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    print("=" * 56)
    print("智谱语音链路冒烟测试：TTS 合成 → ASR 转写 → 与原文比对")
    print("=" * 56)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境准备", "未读取到环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=<你的Key>")

    # ---- 第 1 步：TTS 合成并落盘 ----
    print(f"\n[1/3] TTS 语音合成（model=glm-tts, voice={VOICE}, response_format=wav）")
    print(f"      原文：{ORIGINAL_TEXT}")
    size, duration = synthesize(api_key)
    print(f"      ✔ 音频已保存：{AUDIO_PATH}（{size} 字节，约 {duration:.1f} 秒）")

    # ---- 第 2 步：立刻用 ASR 把同一个文件转写回来 ----
    print("\n[2/3] ASR 语音识别（model=glm-asr-2512，上传刚生成的音频）")
    text = transcribe(api_key)
    print(f"      ✔ 转写结果：{text}")

    # ---- 第 3 步：与原文比对 ----
    print("\n[3/3] 与原文比对")
    exact, ratio = compare(ORIGINAL_TEXT, text)
    print(f"      原文（归一化后）：{normalize(ORIGINAL_TEXT)}")
    print(f"      转写（归一化后）：{normalize(text)}")
    print(f"      逐字一致：{'是' if exact else '否'}；相似度：{ratio:.2f}（通过阈值 {SIMILARITY_THRESHOLD}）")

    if exact or ratio >= SIMILARITY_THRESHOLD:
        print("\n✅ 链路打通：TTS 合成 → 本地落盘 → ASR 转写 → 文本比对，全部成功。")
        sys.exit(0)
    fail("第 3 步 转写文本与原文比对",
         f"相似度 {ratio:.2f} 低于阈值 {SIMILARITY_THRESHOLD}，转写内容与原文偏差过大，链路质量不达标。")


if __name__ == "__main__":
    main()
