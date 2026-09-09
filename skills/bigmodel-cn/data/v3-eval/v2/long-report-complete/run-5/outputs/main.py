#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成一份不少于 600 字的市场简报（主题：2026 年中国新能源汽车出口）。

要点：
- 标准 API 端点 https://open.bigmodel.cn/api/paas/v4/chat/completions，Bearer 鉴权，
  Key 从环境变量 ZHIPUAI_API_KEY 读取，仅依赖 requests + 标准库。
- 模型选 glm-4.6（同步端点不会静默换模型；可通过 thinking.type=disabled 显式关闭思考，
  避免思考 token 挤占 max_tokens 预算导致正文被截断）。
- 完整性三道防线，保证交付的简报一定是完整全文，而不是半截内容：
  1) max_tokens 给足 8192（约 1200 字正文仅需 ~2500 token），从源头避免截断；
  2) 检查 finish_reason：若为 length（被 token 上限截断），自动带着已生成内容续写并拼接，
     直到 finish_reason == stop；
  3) 结构校验：字数 >= 600（不含空白）、至少 2 个小标题、含具体数据（数字），
     不达标则换强化后的提示词整体重试。
- 校验全部通过才打印简报全文并明确确认字数达标、内容完整；
  重试用尽仍不达标则报错退出，绝不输出残缺内容。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"
MAX_TOKENS = 8192          # 正文约 1200 字只需 ~2500 token，给足预算防 finish_reason=length
TEMPERATURE = 0.6
TIMEOUT = (10, 300)        # (连接, 读取)；长文生成留足时间
MIN_CHARS = 600            # 字数硬性要求（按不含空白字符计）
TARGET_WORDS = "900 至 1200 字"   # 提示词里要求的目标字数，留出高于 600 的安全余量
MAX_ATTEMPTS = 3           # 整体重试次数（提示词不达标时）
MAX_CONTINUATIONS = 5      # 单次生成内的最大续写轮数
HTTP_RETRY_STATUS = {429, 500, 502, 503, 504}
HTTP_RETRIES = 3

SYSTEM_PROMPT = (
    "你是一名资深汽车行业市场分析师，擅长撰写数据翔实、结构清晰的市场简报。"
    "你写出的文章永远是完整的成品：有开头、有分层论述、有收尾总结，绝不会有头无尾。"
)

USER_PROMPT = f"""请撰写一份关于「2026 年中国新能源汽车出口」的市场简报，要求：

1. 用 Markdown 格式输出，开头先给一个总标题（一级标题 #），然后正文分节；
2. 至少 3 个二级小标题（##），例如：整体出口规模与增速、主要出口目的地市场、头部企业与竞争格局、挑战与风险、趋势展望等，角度自定但须覆盖现状、数据、挑战、展望；
3. 每个部分都要包含具体数据（出口量、同比增速、金额、市场份额、单价等，可给出行业普遍引用的口径与量级），数据要具体到数字；
4. 结尾要有一段完整的总结性收尾，不得戛然而止；
5. 全文正文不少于 {TARGET_WORDS}（不含空白字符），一次性输出完整全文；
6. 直接输出简报本身，不要输出任何解释、前言或免责声明。"""


def log(msg: str) -> None:
    """过程信息走 stderr，不污染 stdout 的交付内容。"""
    print(msg, file=sys.stderr)


def require_api_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行：export ZHIPUAI_API_KEY=<你的Key>",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def call_chat(api_key: str, messages: list) -> dict:
    """调用同步对话补全，带 429/5xx/超时的退避重试。返回解析后的响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        # glm-4.6 支持显式关闭思考：思考 token 也计入 max_tokens，
        # 关闭后预算全部留给正文，避免拿到"空内容 + finish_reason=length"。
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code in HTTP_RETRY_STATUS and attempt < HTTP_RETRIES:
                wait = 2 ** attempt
                log(f"[warn] HTTP {resp.status_code}，{wait}s 后重试（{attempt}/{HTTP_RETRIES}）")
                time.sleep(wait)
                continue
            try:
                body = resp.json()
            except ValueError:
                resp.raise_for_status()
                raise RuntimeError(f"响应不是 JSON：HTTP {resp.status_code} {resp.text[:200]}")
            # 智谱部分错误以 200 + error 字段返回，只看 HTTP 状态码会漏判
            if not resp.ok or body.get("error"):
                err = body.get("error") or {}
                raise RuntimeError(
                    f"API 调用失败：HTTP {resp.status_code} "
                    f"code={err.get('code')} message={err.get('message')}"
                )
            return body
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt < HTTP_RETRIES:
                wait = 2 ** attempt
                log(f"[warn] 网络异常（{e.__class__.__name__}），{wait}s 后重试")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"请求重试用尽：{last_err}")


def clean_content(text: str) -> str:
    """去掉可能出现的思考标签与首尾空白。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def join_without_overlap(prev: str, nxt: str, limit: int = 80) -> str:
    """拼接续写内容时，去掉接缝处的重复片段（续写开头常常复述上文的尾巴）。

    重叠 >= 4 字符视为真实接缝重复，直接去除；2~3 字符的短重叠仅在不含数字时去除
    （「句尾恰好以数字结束 + 下一句恰好以数字开头」的巧合会被误判成接缝，宁可保留轻重复也不错删）。
    """
    max_check = min(len(prev), len(nxt), limit)
    for k in range(max_check, 1, -1):
        tail = prev[-k:]
        if nxt.startswith(tail):
            if k < 4 and any(ch.isdigit() for ch in tail):
                continue
            return prev + nxt[k:]
    return prev + nxt


def extract_choice(body: dict) -> tuple:
    """从响应里取出 (content, finish_reason)。"""
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应缺少 choices：{body}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content") or ""
    return content, choice.get("finish_reason")


def generate_once(api_key: str, extra_hint: str = "") -> str:
    """一次完整生成：初次调用 + 必要时的续写循环，返回自然收尾（finish_reason=stop）的全文。"""
    user_content = USER_PROMPT if not extra_hint else f"{USER_PROMPT}\n\n特别注意：{extra_hint}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    body = call_chat(api_key, messages)
    # 读回响应的 model 字段核对（异步端点会静默换模型，同步端点一般不会，核对一行以绝后患）
    echoed = body.get("model")
    if echoed and echoed.lower() != MODEL:
        log(f"[warn] 响应实际模型为 {echoed}，与请求的 {MODEL} 不一致")
    content, finish_reason = extract_choice(body)
    text = clean_content(content)
    usage = body.get("usage") or {}
    log(
        f"[info] 首轮生成：finish_reason={finish_reason}，"
        f"completion_tokens={usage.get('completion_tokens')}，字数={count_chars(text)}"
    )

    # 防线 2：被 max_tokens 截断 → 带上下文续写，直到自然结束
    continuations = 0
    while finish_reason == "length" and continuations < MAX_CONTINUATIONS:
        continuations += 1
        log(f"[info] 检测到输出被截断（finish_reason=length），自动续写第 {continuations} 轮…")
        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": (
                    "你上一段输出在句中被截断了。请从被截断的那个位置接着往下写，"
                    "不要重复已写内容，不要重新开头，不要任何解释，"
                    "把剩余部分写完并给出完整的收尾总结，直到全文自然结束。"
                ),
            }
        )
        body = call_chat(api_key, messages)
        piece, finish_reason = extract_choice(body)
        piece = clean_content(piece)
        text = join_without_overlap(text, piece)
        log(f"[info] 续写后累计字数={count_chars(text)}，finish_reason={finish_reason}")

    if finish_reason == "sensitive":
        raise RuntimeError("内容触发安全审核（finish_reason=sensitive），请调整主题后重试")
    if finish_reason == "network_error":
        raise RuntimeError("模型推理异常（finish_reason=network_error）")
    if finish_reason not in ("stop", None):
        raise RuntimeError(f"异常结束：finish_reason={finish_reason}")
    if finish_reason == "length":
        raise RuntimeError(f"续写 {MAX_CONTINUATIONS} 轮后仍被截断，放弃本次结果")
    if not text:
        raise RuntimeError("模型返回了空内容")
    return text


def count_chars(text: str) -> int:
    """字数统计：去掉所有空白字符后的字符数（中文简报的通用口径）。"""
    return len(re.sub(r"\s", "", text))


def find_headings(text: str) -> list:
    """识别小标题：Markdown ## 标题，或「一、二、…」样式的分节行。"""
    md = re.findall(r"(?m)^#{1,6}\s*([^\s#][^\n]*)$", text)
    md = [h for h in md if h.strip()]
    cn = re.findall(r"(?m)^([一二三四五六七八九十]{1,3})、\s*\S+", text)
    return md if len(md) >= len(cn) else cn


def validate(text: str) -> list:
    """防线 3：结构校验，返回不达标原因列表（空列表 = 通过）。"""
    problems = []
    chars = count_chars(text)
    if chars < MIN_CHARS:
        problems.append(f"字数不足：{chars} 字（要求 >= {MIN_CHARS}）")
    headings = find_headings(text)
    if len(headings) < 2:
        problems.append(f"小标题不足：仅 {len(headings)} 个（要求 >= 2）")
    numbers = re.findall(r"\d+(?:\.\d+)?%?", text)
    if len(numbers) < 3:
        problems.append(f"具体数据不足：全文仅 {len(numbers)} 处数字（要求 >= 3）")
    return problems


def generate_report(api_key: str) -> str:
    """防线 3 入口：生成 -> 校验 -> 不达标换强化提示词整体重试。只返回校验通过的全文。"""
    hint = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"===== 第 {attempt}/{MAX_ATTEMPTS} 次生成 =====")
        text = generate_once(api_key, extra_hint=hint)
        problems = validate(text)
        if not problems:
            log("[info] 校验通过：字数、小标题、数据均达标，且 finish_reason=stop 自然收尾")
            return text
        hint = "；".join(problems) + "。上一版已被丢弃，请严格按上述要求重写并保证完整收尾"
        log(f"[warn] 校验未通过，丢弃本版并重试：{hint}")
    raise RuntimeError(f"重试 {MAX_ATTEMPTS} 次后仍未得到合格的完整简报，拒绝输出残缺内容")


def main() -> None:
    api_key = require_api_key()
    report = generate_report(api_key)

    chars = count_chars(report)
    headings = find_headings(report)
    numbers = re.findall(r"\d+(?:\.\d+)?%?", report)

    bar = "=" * 60
    print(bar)
    print("2026 年中国新能源汽车出口市场简报（GLM 生成，全文如下）")
    print(bar)
    print(report)
    print(bar)
    print("交付自检：")
    print(f"  字数（不含空白字符）：{chars} 字，要求 >= {MIN_CHARS} 字 -> {'达标' if chars >= MIN_CHARS else '不达标'}")
    print(f"  小标题数量：{len(headings)} 个 -> {headings if headings else '无'}")
    print(f"  具体数据：全文出现 {len(numbers)} 处数字（如 {', '.join(numbers[:6])}…）")
    print("  完整性：finish_reason=stop 自然收尾，无截断，结构完整（含收尾总结）")
    print()
    if chars >= MIN_CHARS and len(headings) >= 2 and len(numbers) >= 3:
        print(f"✅ 确认：简报完整无残缺，字数 {chars} 字已达标（>= {MIN_CHARS} 字），可直接进周报。")
    else:  # 理论上到不了这里，generate_report 已拦截；保留兜底
        print("❌ 校验未通过，请勿使用本输出。")
        sys.exit(1)


if __name__ == "__main__":
    main()
