#!/usr/bin/env python3
"""智谱语音链路冒烟测试（上线前 smoke test）。

流程：
  1. GLM-TTS 把「发票需要在七个工作日内申请」合成为 wav 音频并保存到本地；
  2. GLM-ASR 立刻把这份音频文件转写回文字；
  3. 打印转写结果并与原文比对，明确报告链路是否打通。

用法：
    export ZHIPUAI_API_KEY=<智谱开放平台标准 API Key>
    python3 main.py

任一步失败都会以非零退出码结束，并说明卡在哪一步、原始报错是什么；
不会只报「已生成音频」就结束。仅依赖 requests + 标准库。
"""

import os
import re
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = f"{API_BASE}/audio/speech"
ASR_URL = f"{API_BASE}/audio/transcriptions"

TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"

ORIGINAL_TEXT = "发票需要在七个工作日内申请"
AUDIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_audio.wav")

TTS_TIMEOUT = 120  # 一句话的合成通常几秒内返回，留足余量
ASR_TIMEOUT = 60   # ASR 限制单文件 ≤25MB、时长 ≤30 秒，本句远小于该限制

# 比对前去掉空白与中英文标点：ASR 可能增删标点，不应因此判转写失败
_NOT_WORD = re.compile(r"[\W_]+", re.UNICODE)


def normalize(text):
    return _NOT_WORD.sub("", text or "")


def fail(step, detail):
    print(f"\n[FAIL] {step}", file=sys.stderr)
    print(f"       {detail.strip() or '(无更多细节)'}", file=sys.stderr)
    print("\n冒烟测试结论：❌ 语音链路未打通，卡在上述步骤。", file=sys.stderr)
    sys.exit(1)


def extract_error(resp):
    """把平台错误响应整理成可读信息：HTTP 状态 + error.code/message。"""
    try:
        body = resp.json()
        err = body.get("error") or body
        return (
            f"HTTP {resp.status_code} | code={err.get('code')} | "
            f"message={err.get('message')!r} | url={resp.url}"
        )
    except ValueError:
        return f"HTTP {resp.status_code} | 非 JSON 响应: {resp.text[:300]!r} | url={resp.url}"


def step1_tts(api_key):
    print(f"[1/3] TTS 合成：POST {TTS_URL}")
    print(f"      model={TTS_MODEL} voice={VOICE} input={ORIGINAL_TEXT!r}")
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": ORIGINAL_TEXT,
                "voice": VOICE,
                "response_format": "wav",  # 非流式才支持 wav；ASR 端正好接受 .wav
                "stream": False,
            },
            timeout=TTS_TIMEOUT,
        )
    except requests.RequestException as exc:
        fail("步骤 1/3 TTS 合成：请求未能完成（网络/代理/DNS 问题？）", repr(exc))

    if resp.status_code != 200:
        fail("步骤 1/3 TTS 合成：接口返回错误", extract_error(resp))

    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type.lower():
        # HTTP 200 但返回 JSON，多半是带 error 体的异常响应，不能当音频落盘
        fail(
            "步骤 1/3 TTS 合成：HTTP 200 但返回的是 JSON 而非音频",
            f"{extract_error(resp)} | Content-Type={content_type}",
        )

    audio = resp.content
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        fail(
            "步骤 1/3 TTS 合成：返回的二进制不是合法 WAV（缺少 RIFF/WAVE 头）",
            f"Content-Type={content_type} | 前 16 字节={audio[:16]!r} | 总长 {len(audio)} 字节",
        )

    with open(AUDIO_PATH, "wb") as f:
        f.write(audio)
    print(f"      ✅ 音频已保存：{AUDIO_PATH}（{len(audio)} 字节）")


def step2_asr(api_key):
    print(f"\n[2/3] ASR 转写：POST {ASR_URL}")
    print(f"      model={ASR_MODEL} file={AUDIO_PATH}")
    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (os.path.basename(AUDIO_PATH), f, "audio/wav")},
                timeout=ASR_TIMEOUT,
            )
    except requests.RequestException as exc:
        fail("步骤 2/3 ASR 转写：请求未能完成（网络/代理/DNS 问题？）", repr(exc))

    if resp.status_code != 200:
        fail("步骤 2/3 ASR 转写：接口返回错误", extract_error(resp))

    try:
        body = resp.json()
    except ValueError:
        fail("步骤 2/3 ASR 转写：响应不是合法 JSON", f"前 300 字节：{resp.text[:300]!r}")

    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        fail("步骤 2/3 ASR 转写：响应中没有可用的 text 字段（转写结果为空）", f"完整响应：{body!r}")

    served_model = body.get("model")
    if served_model and served_model != ASR_MODEL:
        # 部分端点存在静默换模型的情况，读回 model 字段核对
        print(f"      ⚠️ 服务端实际使用的模型是 {served_model}（请求的是 {ASR_MODEL}）")
    print(f"      ✅ 转写结果：{text!r}")
    return text


def step3_compare(transcript):
    print("\n[3/3] 与原文比对")
    print(f"      原文：{ORIGINAL_TEXT!r}")
    print(f"      转写：{transcript!r}")
    norm_orig = normalize(ORIGINAL_TEXT)
    norm_trans = normalize(transcript)
    if norm_orig == norm_trans:
        print(f"      归一化后一致（忽略空白/标点）：{norm_trans!r}")
        print("\n冒烟测试结论：✅ 语音链路已打通（TTS 合成 → 落盘 → ASR 转写 → 回环一致）")
        return
    fail(
        "步骤 3/3 比对：转写内容与原文不一致（音频能合成、也能转写，但回环内容校验未通过）",
        f"归一化后原文：{norm_orig!r}\n       归一化后转写：{norm_trans!r}",
    )


def main():
    print("=" * 62)
    print("智谱语音链路冒烟测试：GLM-TTS 合成 → GLM-ASR 转写 → 回环比对")
    print("=" * 62)

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail(
            "环境准备：缺少 API Key",
            "请先 export ZHIPUAI_API_KEY=<智谱开放平台标准 API Key>（控制台获取："
            "https://bigmodel.cn/usercenter/proj-mgmt/apikeys）。注意：GLM Coding Plan "
            "套餐 Key 与标准 API 隔离，不能调用语音接口，需要用标准 Key。",
        )

    step1_tts(api_key)
    transcript = step2_asr(api_key)
    step3_compare(transcript)


if __name__ == "__main__":
    main()
