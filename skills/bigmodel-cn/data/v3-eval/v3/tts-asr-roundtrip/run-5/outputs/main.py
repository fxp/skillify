#!/usr/bin/env python3
"""智谱语音链路冒烟测试（上线前检查）。

流程：GLM-TTS 把「发票需要在七个工作日内申请」合成音频并落盘为 wav
      -> 立刻用 GLM-ASR 把这个音频文件转写回文字
      -> 打印转写结果并与原文比对，给出链路通/不通的明确结论。

任何一步失败都会报错并说明卡在哪一步，并以非 0 退出码结束；
不会出现"只说已生成音频就算完"的情况。

用法：
    export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>
    python3 main.py
"""

import difflib
import os
import struct
import sys
import unicodedata
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = f"{BASE_URL}/audio/speech"
ASR_URL = f"{BASE_URL}/audio/transcriptions"

TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"        # 系统音色「彤彤」
SAMPLE_RATE = 24000       # 官方文档：GLM-TTS 输出采样率 24000 Hz
SAMPLE_WIDTH = 2          # 16 bit
CHANNELS = 1              # 单声道
ASR_MAX_SECONDS = 30      # ASR 单次限制：<=25MB 且 <=30 秒
TIMEOUT = 120             # 单请求超时（秒）
PASS_SIMILARITY = 0.8     # 归一化文本相似度低于此值视为转写内容异常

TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = Path(__file__).resolve().parent / "tts_asr_roundtrip.wav"

# 常见平台错误码的排查提示（只列实测确认过的）
ERROR_HINTS = {
    "1113": "GLM Coding Plan（编程套餐）Key 与标准 API 不通用，套餐 Key 打标准端点会报 1113；"
            "语音合成/识别请使用 open.bigmodel.cn 控制台创建的标准 API Key。",
}


class StepError(RuntimeError):
    """冒烟测试某一步失败；message 说明卡在哪一步及原始错误信息。"""


def require_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise StepError(
            "[1/4] 环境检查失败：环境变量 ZHIPUAI_API_KEY 未设置。\n"
            "       请先执行 export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key> 再重跑。"
        )
    print(f"[1/4] 环境检查通过：ZHIPUAI_API_KEY 已设置（长度 {len(key)}，值不回显）")
    return key


def describe_error(resp: requests.Response) -> str:
    """把失败响应整理成人能读的错误信息（含平台错误码与排查提示）。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应体非 JSON：{resp.text[:300]!r}"
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        err = body if isinstance(body, dict) else {}
    code = err.get("code", "?")
    message = err.get("message", resp.text[:300])
    line = f"HTTP {resp.status_code}，平台错误码 {code}：{message}"
    hint = ERROR_HINTS.get(str(code))
    if hint:
        line += f"\n       提示：{hint}"
    return line


def wrap_pcm_as_wav(pcm: bytes) -> bytes:
    """给裸 PCM 补 44 字节标准 WAV 头（PCM/24000Hz/16bit/单声道）。"""
    byte_rate = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, CHANNELS, SAMPLE_RATE, byte_rate,
        CHANNELS * SAMPLE_WIDTH, SAMPLE_WIDTH * 8,
        b"data", len(pcm),
    )
    return header + pcm


def wav_duration_seconds(wav: bytes) -> float:
    """按 WAV 头估算时长（秒）；无头时按 24000Hz/16bit/单声道裸 PCM 估算。"""
    if len(wav) >= 44 and wav[:4] == b"RIFF":
        byte_rate = struct.unpack_from("<I", wav, 28)[0] or SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
        data_size = struct.unpack_from("<I", wav, 40)[0] or max(len(wav) - 44, 0)
        return data_size / byte_rate
    return len(wav) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)


def synthesize(api_key: str) -> Path:
    """第 2 步：TTS 合成并落盘为 wav，返回文件路径。"""
    print(f"[2/4] 语音合成（TTS）：{TEXT} -> {AUDIO_PATH.name}")
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": TEXT,
                "voice": VOICE,
                # 关键：接口默认返回裸 PCM（首字节不是 RIFF），裸 PCM 无法直接喂 ASR，
                # 必须显式要求 wav。
                "response_format": "wav",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StepError(f"[2/4] 语音合成失败：请求 {TTS_URL} 网络异常：{exc}") from exc

    if resp.status_code != 200:
        raise StepError(f"[2/4] 语音合成失败（TTS 接口报错）：{describe_error(resp)}")

    audio = resp.content
    content_type = resp.headers.get("Content-Type", "")
    if not audio:
        raise StepError(f"[2/4] 语音合成失败：HTTP 200 但响应体为空（Content-Type={content_type}）")
    if "json" in content_type.lower() or audio.lstrip()[:1] == b"{":
        raise StepError(
            "[2/4] 语音合成失败：HTTP 200 但返回的是 JSON 而非音频"
            f"（Content-Type={content_type}）：{audio[:300].decode('utf-8', 'replace')}"
        )

    if audio[:4] == b"RIFF":
        wav_bytes = audio
    elif content_type.lower().startswith("audio/pcm") or audio[:1] not in (b"R", b"I", b"D"):
        # 自救：已知坑是平台可能无视 response_format 返回裸 PCM（改后缀没用）。
        # 按官方采样率补一个真正的 WAV 头，保证下一步 ASR 能收。
        wav_bytes = wrap_pcm_as_wav(audio)
        print("       注意：接口返回的是裸 PCM 而非 wav，已自动补 WAV 头（24000Hz/16bit/单声道）")
    else:
        raise StepError(
            "[2/4] 语音合成失败：返回的音频格式无法识别"
            f"（前 16 字节 = {audio[:16].hex()}，Content-Type={content_type}），"
            "既不是 RIFF/wav 也不是可补头的裸 PCM。"
        )

    AUDIO_PATH.write_bytes(wav_bytes)
    size = AUDIO_PATH.stat().st_size
    duration = wav_duration_seconds(wav_bytes)
    if size < 1024 or duration < 0.2:
        raise StepError(f"[2/4] 语音合成失败：音频内容异常（{size} 字节，约 {duration:.2f} 秒），疑似空音频")
    if duration > ASR_MAX_SECONDS:
        raise StepError(
            f"[2/4] 语音合成失败：音频约 {duration:.1f} 秒，超过 ASR 单次 30 秒上限，"
            "超长音频需自行分段后分别识别。"
        )
    print(f"       合成成功：{AUDIO_PATH}（{size} 字节，约 {duration:.2f} 秒）")
    return AUDIO_PATH


def transcribe(api_key: str, audio_path: Path) -> str:
    """第 3 步：立刻用 ASR 把刚合成的音频转写回文字。"""
    print(f"[3/4] 语音识别（ASR）：{audio_path.name} -> 文本")
    try:
        with audio_path.open("rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (audio_path.name, f, "audio/wav")},
                timeout=TIMEOUT,
            )
    except requests.RequestException as exc:
        raise StepError(f"[3/4] 语音识别失败：请求 {ASR_URL} 网络异常：{exc}") from exc

    if resp.status_code != 200:
        raise StepError(f"[3/4] 语音识别失败（ASR 接口报错）：{describe_error(resp)}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise StepError(f"[3/4] 语音识别失败：响应不是 JSON：{resp.text[:300]!r}") from exc

    text = str(body.get("text") or "").strip()
    if not text:
        raise StepError(f"[3/4] 语音识别失败：HTTP 200 但转写文本为空，完整响应：{body}")
    print(f"       转写成功：{text}")
    return text


def normalize(text: str) -> str:
    """NFKC 归一（全角转半角等）后去掉标点和空白，只留字母/数字/汉字。

    ASR 可能在句尾自行加标点或把「七」写成「7」，直接逐字比对会误报。
    """
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if ch.isalnum())


def main() -> int:
    print("=" * 66)
    print("智谱语音链路冒烟测试：TTS 合成 -> 本地 wav -> ASR 转写 -> 文本比对")
    print(f"待合成文本：{TEXT}")
    print("=" * 66)

    try:
        api_key = require_api_key()
        audio_path = synthesize(api_key)
        transcript = transcribe(api_key, audio_path)
    except StepError as exc:
        print()
        print("❌ 语音链路未打通，卡在下面这一步：")
        print(f"   {exc}")
        print()
        print("   结论：请按上述错误信息修复后重跑；此步不通，语音链路不具备上线条件。")
        return 1

    print("[4/4] 与原文比对：")
    print(f"   原文     ：{TEXT}")
    print(f"   转写结果 ：{transcript}")
    norm_src = normalize(TEXT)
    norm_asr = normalize(transcript)
    similarity = difflib.SequenceMatcher(a=norm_src, b=norm_asr).ratio()
    exact = norm_src == norm_asr
    if exact:
        print("   归一化后 ：完全一致")
    else:
        print(f"   归一化后 ：存在差异（相似度 {similarity:.3f}）")
        print(f"   归一化原文：{norm_src}")
        print(f"   归一化转写：{norm_asr}")

    print()
    if exact or similarity >= PASS_SIMILARITY:
        print("✅ 语音链路已打通：TTS 合成、本地落盘、ASR 转写、文本回读全部正常。")
        if not exact:
            print(f"   注意：转写与原文非逐字一致（相似度 {similarity:.3f}），")
            print(f"        可播放 {audio_path} 人工确认差异是否可接受。")
        return 0

    print("❌ 语音链路未打通：ASR 有返回，但转写内容与原文差异过大。")
    print(f"   相似度 {similarity:.3f} 低于阈值 {PASS_SIMILARITY}。")
    print(f"   请播放 {audio_path} 人工听一下：若音频正常则是识别质量问题，")
    print("   若音频杂乱/空白则是合成问题，据此定位后重跑。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
