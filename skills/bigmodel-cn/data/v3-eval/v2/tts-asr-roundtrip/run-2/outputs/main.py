#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱语音链路冒烟测试（上线前检查）。

流程：
  1. 调 GLM-TTS（POST /paas/v4/audio/speech）把「发票需要在七个工作日内申请」
     合成为 wav 音频并保存到本脚本同目录；
  2. 立刻调 GLM-ASR-2512（POST /paas/v4/audio/transcriptions）把该音频
     转写回文字；
  3. 打印转写结果并与原文比对，明确报告链路是否打通。

任何一步失败（鉴权、网络、模型报错、音频落盘、转写为空、相似度过低）都会
以非零退出码结束，并指明卡在哪一步——不会只报"已生成音频"。

用法：
    ZHIPUAI_API_KEY=xxx python3 main.py
"""

import difflib
import json
import os
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api"
TTS_URL = f"{API_BASE}/paas/v4/audio/speech"
ASR_URL = f"{API_BASE}/paas/v4/audio/transcriptions"
TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"  # 官方系统音色「彤彤」
REQUEST_TIMEOUT = 120  # 单次 HTTP 请求超时（秒）

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.wav")
# 转写与原文（去标点后）相似度低于该阈值视为回环比对失败
SIMILARITY_PASS_THRESHOLD = 0.8

# 比对前从两侧文本中剔除的标点与空白（ASR 可能加句末标点，TTS 原文没有）
_PUNCTUATIONS = set("""，。！？、；：“”‘’（）《》【】…—\t\r\n ,!?;:"'()[]{}.""")


class StepError(RuntimeError):
    """冒烟测试某一步失败。step 指明卡在哪一步，detail 是具体原因。"""

    def __init__(self, step: str, detail: str):
        super().__init__(f"{step}: {detail}")
        self.step = step
        self.detail = detail


def _describe_http_failure(resp: requests.Response) -> str:
    """把非 2xx 响应整理成人能读的错误描述，尽量带出平台错误码和 message。"""
    try:
        err = resp.json().get("error") or {}
        code, msg = err.get("code", ""), err.get("message", "")
        if code or msg:
            return f"HTTP {resp.status_code}，平台错误码 {code!r}：{msg}"
    except ValueError:
        pass
    snippet = resp.text.strip()[:500] or "<空响应体>"
    return f"HTTP {resp.status_code}，响应体片段：{snippet}"


def _looks_like_json(resp: requests.Response) -> bool:
    ctype = resp.headers.get("Content-Type", "").lower()
    return "json" in ctype or resp.content.lstrip()[:1] == b"{"


def tts_synthesize(api_key: str) -> None:
    """第 1 步：调 GLM-TTS 合成原文，校验后落盘为 wav。"""
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": ORIGINAL_TEXT,
                "voice": VOICE,
                "response_format": "wav",  # 非流式才支持 wav，流式只有 pcm
                "speed": 1.0,
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StepError("TTS 合成", f"请求发送失败（网络问题或超时）：{exc}") from exc

    if resp.status_code != 200:
        raise StepError("TTS 合成", _describe_http_failure(resp))
    # 防"HTTP 200 但返回的是 JSON 报错而不是音频"的静默失败
    if _looks_like_json(resp):
        raise StepError("TTS 合成", f"接口返回了 JSON 而非音频，疑似报错：{resp.text[:500]}")
    if resp.content[:4] != b"RIFF" or resp.content[8:12] != b"WAVE":
        raise StepError("TTS 合成", f"返回内容不是有效的 WAV 文件（文件头 {resp.content[:12]!r}）")

    try:
        with open(AUDIO_PATH, "wb") as f:
            f.write(resp.content)
    except OSError as exc:
        raise StepError("TTS 合成", f"音频写入本地失败（{AUDIO_PATH}）：{exc}") from exc

    size = os.path.getsize(AUDIO_PATH)
    if size < 1000:  # 一整句话的正常 wav 远大于 1KB
        raise StepError("TTS 合成", f"音频文件异常地小（仅 {size} 字节），疑似合成失败")


def asr_transcribe(api_key: str) -> str:
    """第 2 步：把刚生成的 wav 上传给 GLM-ASR-2512，返回转写文本。"""
    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL, "stream": "false"},
                files={"file": (os.path.basename(AUDIO_PATH), f, "audio/wav")},
                timeout=REQUEST_TIMEOUT,
            )
    except OSError as exc:
        raise StepError("ASR 转写", f"音频读取失败（{AUDIO_PATH}）：{exc}") from exc
    except requests.RequestException as exc:
        raise StepError("ASR 转写", f"请求发送失败（网络问题或超时）：{exc}") from exc

    if resp.status_code != 200:
        raise StepError("ASR 转写", _describe_http_failure(resp))

    try:
        data = resp.json()
    except ValueError as exc:
        raise StepError("ASR 转写", f"响应不是合法 JSON：{resp.text[:500]}") from exc

    # 个别接口 HTTP 200 也会带 error 体，不能只看状态码
    if isinstance(data, dict) and data.get("error"):
        raise StepError("ASR 转写", f"平台返回错误：{data['error']}")

    text = data.get("text", "") if isinstance(data, dict) else ""
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        body = json.dumps(data, ensure_ascii=False)[:500]
        raise StepError("ASR 转写", f"转写结果为空（音频没能转出文字），完整响应：{body}")
    return text


def normalize(text: str) -> str:
    """去掉标点和空白，只剩实质文字，用于公平比对。"""
    return "".join(ch for ch in text if ch not in _PUNCTUATIONS)


def fail(exc: StepError) -> int:
    print(f"\n❌ 冒烟测试失败：卡在【{exc.step}】这一步，链路未打通。", file=sys.stderr)
    print(f"   具体原因：{exc.detail}", file=sys.stderr)
    return 1


def main() -> int:
    # 管道/重定向时让 stdout 按行刷新，保证与 stderr 的输出顺序不乱
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    print("=" * 62)
    print("智谱语音链路冒烟测试：TTS 合成 → ASR 转写 → 与原文比对")
    print("=" * 62)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("❌ 环境变量 ZHIPUAI_API_KEY 未设置或为空，测试无法开始。", file=sys.stderr)
        print("   请先执行：export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>", file=sys.stderr)
        return 1

    # ---- 第 1 步：TTS 合成并落盘 ----
    print(f"\n[1/3] 调用 {TTS_MODEL} 合成：{ORIGINAL_TEXT}")
    try:
        tts_synthesize(api_key)
    except StepError as exc:
        return fail(exc)
    print(f"      ✔ 音频已保存：{AUDIO_PATH}（{os.path.getsize(AUDIO_PATH)} 字节）")

    # ---- 第 2 步：立刻用 ASR 转写该音频 ----
    print(f"\n[2/3] 调用 {ASR_MODEL} 转写刚生成的音频 …")
    try:
        transcribed = asr_transcribe(api_key)
    except StepError as exc:
        return fail(exc)
    print(f"      ✔ 转写结果：{transcribed}")

    # ---- 第 3 步：与原文比对 ----
    print("\n[3/3] 转写结果与原文比对")
    norm_original = normalize(ORIGINAL_TEXT)
    norm_transcribed = normalize(transcribed)
    similarity = difflib.SequenceMatcher(None, norm_original, norm_transcribed).ratio()
    exact = norm_original == norm_transcribed
    print(f"      原文（去标点）：{norm_original}")
    print(f"      转写（去标点）：{norm_transcribed}")
    print(f"      逐字一致：{'是' if exact else '否'}    相似度：{similarity:.0%}")

    if similarity < SIMILARITY_PASS_THRESHOLD:
        print("\n❌ 冒烟测试失败：卡在【第 3 步 回环比对】这一步，链路不能视为打通。", file=sys.stderr)
        print(f"   转写结果与原文差异过大（相似度 {similarity:.0%} < 阈值 "
              f"{SIMILARITY_PASS_THRESHOLD:.0%}），TTS 或 ASR 至少一端产出异常。", file=sys.stderr)
        return 1

    tag = "完全一致" if exact else f"相似度 {similarity:.0%}，达到阈值"
    print(f"\n✅ 语音链路已打通（{tag}）：TTS 合成 → 音频落盘 → ASR 转写 → 内容比对全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
