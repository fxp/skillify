#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM（glm-5.3）生成「2026 年中国新能源汽车出口」市场简报。

要求：不少于 600 字、有小标题、有具体数据，且必须完整——不许写到一半断掉。

完整性策略（对应 bigmodel-cn 技能包实测坑位 #13 / #14）：
  * glm-5.3 在标准端点深度思考强制开启，且思考 token 计入 max_tokens——预算给足
    （MAX_TOKENS=16384），并用 reasoning_effort="low" 压低思考消耗；标准端点
    thinking 关不掉（传 {"type":"disabled"} 会报 1210），所以干脆不传该参数。
  * 是否被截断只看 finish_reason（== "length" 即截断），不看 content 是否为空：
    预算被思考吃光时 content 可能是空串但 finish_reason=length。
  * 一旦截断，就带着已写内容续写（多轮拼接、接缝去重），直到 finish_reason=stop
    且正文以句末标点自然收尾。
  * 成稿后终检：字数（不含空白）≥600、小标题 ≥3、具体数据 ≥5 处、完整收尾；
    任一不达标整体重写，全部失败则报错退出——绝不把半截内容当成功交付。

用法：ZHIPUAI_API_KEY=你的Key python3 main.py
依赖：仅 requests。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

MAX_TOKENS = 16384        # 输出 token 上限（思考 token 也算在内），远超 600 字所需
REASONING_EFFORT = "low"  # glm-5.3 标准端点仅接受 low/high/max；思考关不掉只能调强度
TEMPERATURE = 0.6
REQUEST_TIMEOUT = (10, 300)  # 思考型模型生成长文较慢，读超时给足

MIN_CHARS = 600           # 字数下限（按不含空白字符计）
MIN_HEADINGS = 3          # 小标题数量下限
MIN_NUMBERS = 5           # 具体数据（数字）处数下限
TARGET_CHARS = 800        # 提示词中的目标字数，留缓冲防压线

MAX_CONT_ROUNDS = 4       # 单次成稿内最多续写轮数（外加首发 1 次）
MAX_FULL_RETRIES = 3      # 终检不过时的整体重写次数
MAX_HTTP_RETRIES = 3      # 网络/限流等传输层重试次数

TERMINAL_PUNCT = tuple("。！？；!?;”』」）)")

HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*\S|[一二三四五六七八九十]+、\s*\S|【[^】]{2,20}】\s*$)",
    re.M,
)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")

SYSTEM_PROMPT = (
    "你是一名新能源汽车行业的资深市场分析师，为公司周报撰写市场简报。"
    "你的输出必须是纯 Markdown 正文本身：以一个一级标题（# ）开头，正文分成多个"
    "二级小标题（## ）小节；不要输出任何与正文无关的内容（不要解释、不要寒暄、"
    "不要用代码块包裹）。必须一次性把整篇简报写完，结尾自然收束，不许中途停笔。"
)


def build_user_prompt():
    return (
        "请撰写一份主题为「2026 年中国新能源汽车出口」的市场简报，要求：\n"
        f"1. 正文不少于 {TARGET_CHARS} 字；\n"
        f"2. 至少 {MIN_HEADINGS} 个二级小标题（格式「## 小标题」），建议覆盖：出口总量与增速、"
        "主要目的地市场、出口结构（整车/动力电池/零部件）、海运运力与本地化布局、"
        "风险与展望等；\n"
        "3. 每个小节都必须有具体数据（销量、金额、增速、占比、排名等，数字要带单位），"
        "基于你掌握的行业趋势给出自洽的具体估计即可；\n"
        "4. 结尾用一小段总结收束全文，不要在句子中间停住。\n"
        "现在直接输出简报全文。"
    )


CONT_PROMPT = (
    "上面的简报还没有写完，在句中被截断了。请从你停下来的那个字接着往下写，"
    "把整篇简报补充完整：不要重复已写过的任何内容，不要重新开头，"
    "不要加「（续）」之类的标记，直接输出紧接上文的正文，"
    "并把最后一个小节写完、以一段总结自然收束。"
)


# ---------------------------------------------------------------- 文本度量 --

def count_chars(text):
    """字数 = 不含空白字符的字符数（中文简报的通行口径「字数（不计空格」）。"""
    return sum(1 for c in text if not c.isspace())


def count_headings(text):
    return len(HEADING_RE.findall(text))


def count_numbers(text):
    return len(NUMBER_RE.findall(text))


def ends_cleanly(text):
    return text.rstrip().endswith(TERMINAL_PUNCT)


def validate(text):
    """返回不达标项列表；空列表 = 全部达标。"""
    problems = []
    if count_chars(text) < MIN_CHARS:
        problems.append(f"字数不足（{count_chars(text)} < {MIN_CHARS}）")
    if count_headings(text) < MIN_HEADINGS:
        problems.append(f"小标题不足（{count_headings(text)} < {MIN_HEADINGS}）")
    if count_numbers(text) < MIN_NUMBERS:
        problems.append(f"具体数据不足（{count_numbers(text)} < {MIN_NUMBERS}）")
    if not ends_cleanly(text):
        problems.append(f"结尾疑似截断（末字符 {text.rstrip()[-1:]!r}）")
    return problems


# ---------------------------------------------------------------- 文本清洗 --

def clean_text(text):
    """去掉首尾空白与误加的 Markdown 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip("`").strip().lower() in ("", "markdown", "md"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def strip_overlap(prev, nxt, window=100):
    """续写接缝去重：模型续写时常把结尾几个字再打一遍，裁掉重复前缀。"""
    max_k = min(len(prev), len(nxt), window)
    for k in range(max_k, 0, -1):
        if prev.endswith(nxt[:k]):
            return nxt[k:]
    return nxt


# ---------------------------------------------------------------- API 调用 --

def call_glm(messages):
    """同步对话补全，返回 (content, finish_reason)。传输层错误自动重试。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": MAX_TOKENS,
        "reasoning_effort": REASONING_EFFORT,
        "temperature": TEMPERATURE,
    }
    last_err = None
    for attempt in range(MAX_HTTP_RETRIES):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络异常：{exc}"
        else:
            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                return message.get("content") or "", choice.get("finish_reason") or ""
            try:
                err = resp.json().get("error", {})
                detail = f"code={err.get('code')} message={err.get('message')}"
            except ValueError:
                detail = resp.text[:200]
            # 401（Key 无效）、400（参数错）等重试无意义；408/429/5xx 值得重试
            if resp.status_code not in (408, 429) and not 500 <= resp.status_code < 600:
                raise RuntimeError(f"API 返回 HTTP {resp.status_code}（{detail}）")
            last_err = f"HTTP {resp.status_code}（{detail}）"
        if attempt < MAX_HTTP_RETRIES - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"请求连续 {MAX_HTTP_RETRIES} 次失败：{last_err}")


def generate_once():
    """一次成稿：被截断就带上下文续写拼接，返回 (text, 调用次数, 最后finish_reason)。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt()},
    ]
    text = ""
    finish = ""
    empty_hits = 0
    for rnd in range(1, MAX_CONT_ROUNDS + 2):  # 首发 1 次 + 最多 MAX_CONT_ROUNDS 次续写
        content, finish = call_glm(messages)
        if not content.strip():
            # content 为空且 finish_reason=length：预算被思考吃光的典型表现，
            # 换一轮重试（本轮 messages 不变，不消耗上下文结构）
            empty_hits += 1
            if empty_hits > 2:
                raise RuntimeError(
                    f"连续拿到空内容（finish_reason={finish}），"
                    f"思考 token 可能吃光了 max_tokens 预算，请调大 MAX_TOKENS"
                )
            continue
        piece = clean_text(content)
        if text:
            piece = strip_overlap(text, piece)
        text = (text + piece).strip()

        if finish == "sensitive":
            raise RuntimeError("内容触发平台安全拦截（finish_reason=sensitive）")
        if finish == "model_context_window_exceeded":
            raise RuntimeError("超出模型上下文窗口（finish_reason=model_context_window_exceeded）")

        if finish == "stop" and ends_cleanly(text):
            return text, rnd, finish
        # finish_reason=length（真截断）、stop 但没收尾、network_error 但有部分内容：
        # 都走续写，把残缺内容在内部消化掉
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": CONT_PROMPT},
        ]
    if not text:
        raise RuntimeError("多轮调用后仍未生成任何内容")
    return text, MAX_CONT_ROUNDS + 1, finish


# -------------------------------------------------------------------- 主流程 --

def deliver(text, rounds, finish):
    """打印简报全文与校验结论。"""
    line = "=" * 62
    print(line)
    print("2026 年中国新能源汽车出口 · 市场简报（智谱 GLM 生成）")
    print(line)
    print(text)
    print(line)
    print("校验结果")
    print(line)

    def ok(cond):
        return "达标" if cond else "不达标"

    chars, heads, nums = count_chars(text), count_headings(text), count_numbers(text)
    print(f"  字数（不含空白字符）：{chars} 字（要求 >= {MIN_CHARS}）—— {ok(chars >= MIN_CHARS)}")
    print(f"  小标题数量：{heads} 个（要求 >= {MIN_HEADINGS}）—— {ok(heads >= MIN_HEADINGS)}")
    print(f"  具体数据出现：{nums} 处（要求 >= {MIN_NUMBERS}）—— {ok(nums >= MIN_NUMBERS)}")
    print(f"  最后一轮 finish_reason：{finish}，结尾字符：{text.rstrip()[-1:]!r}"
          f"—— {ok(finish == 'stop' and ends_cleanly(text))}")
    print(f"  生成调用次数：{rounds}（含续写拼接，接缝已去重）")
    print(line)
    print("结论：简报字数达标、内容完整（含小标题与具体数据、完整收尾），可直接进周报。")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）", file=sys.stderr)
        return 1

    for attempt in range(1, MAX_FULL_RETRIES + 1):
        try:
            text, rounds, finish = generate_once()
        except RuntimeError as exc:
            print(f"[尝试 {attempt}/{MAX_FULL_RETRIES}] 生成失败：{exc}", file=sys.stderr)
            continue
        problems = validate(text)
        if not problems:
            return deliver(text, rounds, finish)
        print(f"[尝试 {attempt}/{MAX_FULL_RETRIES}] 成稿未达标：{'；'.join(problems)}，整体重写",
              file=sys.stderr)

    print(f"错误：连续 {MAX_FULL_RETRIES} 次都未得到达标的完整简报，已放弃（未输出残缺内容）",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
