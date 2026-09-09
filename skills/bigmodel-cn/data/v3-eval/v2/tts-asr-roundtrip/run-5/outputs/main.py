#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱语音链路冒烟测试（上线前 smoke test）

流程：
  1. 从环境变量 ZHIPUAI_API_KEY 读取鉴权 Key
  2. 调 GLM-TTS 把「发票需要在七个工作日内申请」合成为 WAV 音频，落盘到脚本同目录
  3. 立刻把该音频文件发给 GLM-ASR-2512 转写回文字
  4. 打印转写结果并与原文比对，给出「链路通 / 不通」的明确结论

任何一步失败都会带着步骤编号和错误详情以退出码 1 结束，
不会出现「只说生成了音频就算完」的情况。

依赖：仅 requests（pip install requests）
用法：python3 main.py
"""

import difflib
import os
import re
import sys

import requests

# ---------- 常量 ----------
API_BASE = "https://open.bigmodel.cn/api/paas/v4"
TTS_URL = f"{API_BASE}/audio/speech"
ASR_URL = f"{API_BASE}/audio/transcriptions"
TTS_MODEL = "glm-tts"
ASR_MODEL = "glm-asr-2512"
VOICE = "tongtong"  # 系统默认音色「彤彤」
TEXT = "发票需要在七个工作日内申请"
SIMILARITY_PASS = 0.90  # 归一化后相似度达到该阈值判定内容一致
REQUEST_TIMEOUT = 120  # 秒

AUDIO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tts_smoke_test.wav"
)


def log(*args, **kwargs):
    """输出统一带 flush，保证被管道/tee 重定向时与 stderr 顺序稳定。"""
    print(*args, flush=True, **kwargs)


def fail(step, detail):
    """带步骤信息终止脚本，明确指出链路卡在哪一步。"""
    log(f"\n❌ 语音链路未打通：卡在【{step}】", file=sys.stderr)
    log(f"   详情: {detail}", file=sys.stderr)
    sys.exit(1)


def api_error_detail(resp):
    """把平台返回的错误响应整理成人能读的一句话。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:200]!r}"
    err = body.get("error") if isinstance(body, dict) else None
    code = (err or {}).get("code") or body.get("code")
    message = (err or {}).get("message") or body.get("msg") or str(body)[:200]
    detail = f"HTTP {resp.status_code}，错误码 {code}：{message}"
    if str(code) == "1113":
        detail += (
            "（提示：1113 常见于拿 GLM Coding Plan 套餐 Key 打标准端点，"
            "本脚本需要标准 API Key）"
        )
    return detail


def step_tts(api_key):
    """步骤 2：TTS 合成并落盘。"""
    log(f"[2/4] 调用 {TTS_MODEL} 合成音频 ...")
    try:
        resp = requests.post(
            TTS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": TTS_MODEL,
                "input": TEXT,
                "voice": VOICE,
                "response_format": "wav",  # 非流式支持 wav，可直接回传 ASR
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        fail("TTS 语音合成（请求未发出或网络异常）", repr(exc))

    if resp.status_code != 200:
        fail("TTS 语音合成", api_error_detail(resp))

    # TTS 成功时返回的是二进制音频；若返回 JSON 说明平台报了错（HTTP 200 也可能是错误体）
    if "json" in resp.headers.get("Content-Type", "").lower():
        fail("TTS 语音合成（接口返回 JSON 错误体而非音频）", api_error_detail(resp))

    audio = resp.content
    if len(audio) < 44 or audio[:4] != b"RIFF":
        fail(
            "TTS 语音合成（音频校验）",
            f"返回的 {len(audio)} 字节不是有效 WAV 数据（缺少 RIFF 头）",
        )

    with open(AUDIO_PATH, "wb") as f:
        f.write(audio)
    log(f"      OK：已写入 {AUDIO_PATH}（{len(audio)} 字节）")


def step_asr(api_key):
    """步骤 3：把刚生成的音频文件发给 ASR 转写。"""
    log(f"[3/4] 调用 {ASR_MODEL} 把音频转写回文字 ...")
    try:
        with open(AUDIO_PATH, "rb") as f:
            resp = requests.post(
                ASR_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": ASR_MODEL},
                files={"file": (os.path.basename(AUDIO_PATH), f, "audio/wav")},
                timeout=REQUEST_TIMEOUT,
            )
    except requests.RequestException as exc:
        fail("ASR 语音识别（请求未发出或网络异常）", repr(exc))

    if resp.status_code != 200:
        fail("ASR 语音识别", api_error_detail(resp))

    try:
        body = resp.json()
    except ValueError:
        fail("ASR 语音识别（响应解析）", f"响应不是 JSON：{resp.text[:200]!r}")

    text = (body.get("text") or "").strip() if isinstance(body, dict) else ""
    if not text:
        fail("ASR 语音识别（转写结果为空）", f"接口返回：{body}")
    log(f"      OK：转写结果 -> {text}")
    return text


def normalize(text):
    """去掉标点和空白，只留文字本身，避免标点差异干扰比对。"""
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def step_compare(transcribed):
    """步骤 4：与原文比对并给出结论。"""
    log("[4/4] 与原文比对 ...")
    a, b = normalize(TEXT), normalize(transcribed)
    similarity = difflib.SequenceMatcher(None, a, b).ratio()
    log(f"      原文     : {TEXT}")
    log(f"      转写     : {transcribed}")
    log(f"      归一化后 : {b}")
    log(f"      相似度   : {similarity:.0%}")

    if a == b:
        log("\n✅ 语音链路已打通：TTS 合成 -> 本地 WAV -> ASR 转写，内容与原文完全一致。")
        return
    if similarity >= SIMILARITY_PASS:
        log(
            f"\n✅ 语音链路已打通：转写内容与原文基本一致（相似度 {similarity:.0%}，"
            "差异可能来自标点或同音字，原文/转写均已打印，建议人工复核）。"
        )
        return
    fail(
        "结果比对（能合成也能转写，但转写内容与原文偏差过大）",
        f"相似度仅 {similarity:.0%}（阈值 {SIMILARITY_PASS:.0%}），"
        f"原文「{TEXT}」vs 转写「{transcribed}」",
    )


def main():
    log("=== 智谱语音链路冒烟测试（TTS -> 本地音频 -> ASR 回读） ===")
    log("[1/4] 检查环境变量 ZHIPUAI_API_KEY ...")
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail(
            "环境变量检查（尚未发出任何请求）",
            "未设置 ZHIPUAI_API_KEY。请先执行：export ZHIPUAI_API_KEY=<你的标准 API Key>",
        )
    log("      OK")

    step_tts(api_key)
    transcribed = step_asr(api_key)
    step_compare(transcribed)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：任何未预期异常也归因到冒烟测试失败
        fail("未预期的异常（脚本层面，不一定是平台问题）", repr(exc))
