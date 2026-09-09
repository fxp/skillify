#!/usr/bin/env python3
"""智谱语音链路冒烟测试（上线前检查）。

流程：GLM-TTS 把「发票需要在七个工作日内申请」合成 wav 落盘
     → 立刻用 GLM-ASR-2512 把这个音频文件转写回文字
     → 打印转写结果并与原文比对，明确报告链路是否打通。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
退出码：0 = 链路打通；1 = 任一步失败（输出会指明卡在哪一步、为什么）。
"""

import difflib
import os
import re
import struct
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
TTS_URL = BASE_URL + "/paas/v4/audio/speech"
ASR_URL = BASE_URL + "/paas/v4/audio/transcriptions"

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = "tts_output.wav"      # 保存在当前工作目录
TTS_VOICE = "tongtong"             # 系统音色「彤彤」
ASR_MAX_BYTES = 25 * 1024 * 1024   # ASR 限制：文件 ≤25MB
ASR_MAX_SECONDS = 30.0             # ASR 限制：时长 ≤30 秒
SIMILARITY_PASS = 0.80             # 归一化后相似度达到该阈值即视为转写通过


class StepFailure(Exception):
    """某一步失败；message 必须说清楚卡在哪一步、原因是什么。"""


def http_error_detail(resp):
    """把平台错误响应（{"error":{"code","message"}}）拼成人能看的话。"""
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        err = {}
    if err.get("code") or err.get("message"):
        return f"平台返回错误 code={err.get('code')} message={err.get('message')}（HTTP {resp.status_code}）"
    return f"HTTP {resp.status_code}，响应体前 200 字节：{resp.text[:200]!r}"


def synthesize(api_key):
    """第 1 步：调 GLM-TTS，返回音频字节。"""
    print("[1/4] 调用 GLM-TTS 合成语音 ...")
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "glm-tts",
                "input": ORIGINAL_TEXT,
                "voice": TTS_VOICE,
                "response_format": "wav",  # wav 仅非流式可用（流式只支持 pcm）
                "stream": False,
            },
            timeout=(10, 60),
        )
    except requests.RequestException as exc:
        raise StepFailure("TTS 请求", f"网络/接口异常：{exc!r}") from exc
    if resp.status_code != 200:
        raise StepFailure("TTS 请求", http_error_detail(resp))
    # TTS 成功时响应是音频二进制；若拿到 JSON，说明平台回的错误体（存在 HTTP 200 仍回错误的情况），
    # 此时绝不能把 JSON 当音频落盘，否则会到 ASR 那一步才莫名其妙地失败。
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type.lower() or resp.content[:1] == b"{":
        raise StepFailure(
            "TTS 响应校验",
            f"期望音频二进制却拿到 JSON（Content-Type: {content_type}）：{resp.text[:300]}",
        )
    if not resp.content.startswith(b"RIFF"):
        raise StepFailure(
            "TTS 响应校验",
            f"响应不是合法 WAV（缺少 RIFF 头），前 16 字节：{resp.content[:16]!r}",
        )
    print(f"      合成成功，收到 {len(resp.content)} 字节音频")
    return resp.content


def wav_duration(data):
    """走查 RIFF 块估算 WAV 时长（秒）；结构非标准时返回 None，只影响提示不影响成败。"""
    try:
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None
        pos, byte_rate = 12, None
        while pos + 8 <= len(data):
            chunk_id = data[pos:pos + 4]
            size = struct.unpack_from("<I", data, pos + 4)[0]
            if chunk_id == b"fmt ":
                byte_rate = struct.unpack_from("<I", data, pos + 16)[0]  # fmt 块第 9-12 字节：ByteRate
            elif chunk_id == b"data":
                return size / byte_rate if byte_rate else None
            pos += 8 + size + (size & 1)  # RIFF 块按 2 字节对齐
        return None
    except struct.error:
        return None


def save_and_inspect(audio_bytes):
    """第 2 步：音频落盘，并预先检查 ASR 的输入限制，避免上传才被拒。"""
    print(f"[2/4] 音频落盘 {os.path.abspath(AUDIO_PATH)} ...")
    try:
        with open(AUDIO_PATH, "wb") as f:
            f.write(audio_bytes)
    except OSError as exc:
        raise StepFailure("音频落盘", f"写文件失败：{exc}") from exc
    if len(audio_bytes) > ASR_MAX_BYTES:
        raise StepFailure("音频落盘校验", f"文件 {len(audio_bytes)} 字节超过 ASR 的 25MB 上限")
    duration = wav_duration(audio_bytes)
    if duration is None:
        print(f"      已写入 {len(audio_bytes)} 字节（未能解析时长，跳过时长检查）")
    else:
        if duration > ASR_MAX_SECONDS:
            raise StepFailure("音频落盘校验", f"音频约 {duration:.1f} 秒，超过 ASR 的 30 秒上限")
        print(f"      已写入 {len(audio_bytes)} 字节，时长约 {duration:.2f} 秒（在 ASR 30 秒限制内）")
    return AUDIO_PATH


def transcribe(api_key, path):
    """第 3 步：把刚生成的音频文件喂给 GLM-ASR-2512，返回转写文本。"""
    print("[3/4] 调用 GLM-ASR-2512 转写刚生成的音频 ...")
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": "glm-asr-2512", "stream": "false"},
                files={"file": (os.path.basename(path), f, "audio/wav")},
                timeout=(10, 120),
            )
    except OSError as exc:
        raise StepFailure("ASR 请求", f"读取音频文件失败：{exc}") from exc
    except requests.RequestException as exc:
        raise StepFailure("ASR 请求", f"网络/接口异常：{exc!r}") from exc
    if resp.status_code != 200:
        raise StepFailure("ASR 请求", http_error_detail(resp))
    try:
        body = resp.json()
    except ValueError as exc:
        raise StepFailure("ASR 响应解析", f"响应不是合法 JSON：{resp.text[:200]!r}") from exc
    # 读回响应里的 model 字段核对（平台存在静默换模型的情况，不能只信请求参数）
    print(f"      ASR 响应 model 字段：{body.get('model')}")
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise StepFailure("ASR 响应校验", f"转写结果为空（text 缺失或为空），完整响应：{body}")
    print(f"      转写结果：{text}")
    return text


# 归一化：去掉空白与中英文标点；ASR 可能把「七」写成数字「7」，统一转成汉字再比。
# 注意只做单字符映射（"10"→"一〇"），对本文这句固定文本足够。
_STRIP_RE = re.compile(r"[\s　，。！？、；：“”‘’（）《》…·,.!?;:'\"()\[\]{}<>—-]+")
_DIGIT_MAP = str.maketrans("0123456789０１２３４５６７８９", "零一二三四五六七八九" * 2)


def normalize(text):
    return _STRIP_RE.sub("", text).translate(_DIGIT_MAP)


def compare(transcribed):
    """第 4 步：与原文比对，返回 (是否通过, 相似度)。"""
    print("[4/4] 与原文比对 ...")
    a, b = normalize(ORIGINAL_TEXT), normalize(transcribed)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    print(f"      原文：{ORIGINAL_TEXT}")
    print(f"      转写：{transcribed}")
    if a == b:
        print("      归一化后完全一致")
    else:
        print(f"      归一化后：原文={a} | 转写={b}")
        print(f"      相似度：{ratio:.0%}")
    return ratio >= SIMILARITY_PASS, ratio


def main():
    sys.stdout.reconfigure(line_buffering=True)  # 重定向时保证进度输出与 stderr 错误信息顺序不乱
    print(f"智谱语音链路冒烟测试：原文「{ORIGINAL_TEXT}」")
    print("=" * 56)
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("[FAIL] 冒烟测试未通过，卡在【读取环境变量】：未设置 ZHIPUAI_API_KEY，"
              "拿不到 Key 就无法调用任何接口（export ZHIPUAI_API_KEY=... 后重试）", file=sys.stderr)
        return 1
    try:
        audio = synthesize(api_key)
        path = save_and_inspect(audio)
        transcribed = transcribe(api_key, path)
    except StepFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    ok, ratio = compare(transcribed)
    print("=" * 56)
    if ok:
        verdict = ("转写与原文归一化后完全一致" if ratio == 1.0
                   else f"转写与原文相似度 {ratio:.0%}，达到 {SIMILARITY_PASS:.0%} 通过阈值（差异来自标点/数字写法）")
        print(f"[PASS] 语音链路打通：TTS 合成 → 本地 wav（{os.path.abspath(AUDIO_PATH)}）→ ASR 转写 → 比对。{verdict}")
        return 0
    print("[FAIL] 冒烟测试未通过，卡在【文本比对】：TTS 与 ASR 两步接口本身都成功了，"
          f"但转写结果与原文偏差过大（相似度 {ratio:.0%}，低于 {SIMILARITY_PASS:.0%} 阈值）。"
          f"建议人工听一下 {os.path.abspath(AUDIO_PATH)}，看是合成含糊还是识别出错，再对症处理。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
