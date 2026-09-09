#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 年中国新能源汽车出口市场简报生成器

用法：ZHIPUAI_API_KEY=xxx python3 main.py

设计与硬约束的对应关系：
- 网关硬限制：单次请求 max_tokens 绝不能超过 1000。
  本脚本用"分段生成"绕开限制：每次请求只写一个小节（max_tokens=700，
  远低于 1000 的硬上限），全部小节在本地拼接成完整正文；字数不足时再对
  最短的小节发起续写请求（max_tokens 同样不超过 1000），直到达标。
- 模型选 glm-4.6 并显式传 thinking.type=disabled：
  官方文档确认 GLM-5.3 / GLM-5.3-FLASH 在标准端点强制开启思考，且思考
  token 计入 max_tokens——在 1000 的预算下极易出现 finish_reason=length、
  正文为空串；glm-4.6 属于"自动判断是否思考"的模型，允许显式关闭。
- 走同步端点 /paas/v4/chat/completions（异步端点会静默更换模型）。
- 每次请求都检查 finish_reason 而不是只看内容是否为空；
  任一环节失败都会明确报告卡在哪（HTTP 状态 / 平台错误码 / finish_reason），
  不输出半成品。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"  # thinking 可显式关闭；勿换 glm-5.3（标准端点强制思考，会挤占 max_tokens）

MAX_TOKENS_CAP = 1000     # 网关硬上限：任何请求的 max_tokens 都必须 <= 它
SECTION_MAX_TOKENS = 700  # 单次请求实际申请的生成额度（一小节正文绰绰有余，且低于硬上限）
REQUEST_TIMEOUT = 60
RETRY_TIMES = 2           # 网络/5xx 重试次数
TARGET_HAN = 600          # 正文汉字数下限
CORE_SECTIONS = 4         # 前 4 节是简报核心叙事，无论字数是否提前达标都完整生成
MAX_TOTAL_REQUESTS = 8    # 全程请求数上限，防止扩写循环失控

TITLE = "2026 年中国新能源汽车出口市场简报"

# 每个小节的 (小标题, 内容要求)。
SECTIONS = [
    ("一、总体规模与增长态势",
     "概述 2026 年中国新能源汽车出口的整车出口量（万辆）、同比增速、出口金额，"
     "以及在全球新能源汽车贸易中的占比，至少给出 3 个具体数据。"),
    ("二、区域市场结构",
     "分析 2026 年中国新能源汽车出口的目的地结构：欧洲、东南亚、拉美、中东等"
     "主要市场的占比与增速，以及 KD 组装、海外建厂等本地化动向，至少给出 3 个具体数据。"),
    ("三、车企竞争格局",
     "描述 2026 年主要出口车企（如比亚迪、奇瑞、上汽、吉利等）的出口表现、"
     "梯队分化，以及插电混动与纯电动的结构变化，至少给出 3 个具体数据。"),
    ("四、机遇与挑战",
     "分析 2026 年出口面临的欧盟关税与本地化要求、海运运力与汇率波动、"
     "海外销售与服务网络建设等挑战，以及新兴市场的增长机遇，至少给出 2 个具体数据。"),
    ("五、全年趋势展望",
     "展望 2026 全年及下一年的出口量级、动力结构与竞争要点，"
     "给出量化的预期区间，至少给出 2 个具体数据。"),
]

SECTION_PROMPT_TMPL = (
    "你是资深汽车行业市场分析师。请为《{title}》撰写小节「{heading}」的正文，要求：\n"
    "1. 只输出这一小节的正文，不要复述小标题，不要写引言、总结或任何客套话；\n"
    "2. 220 汉字左右（180—280 之间）；\n"
    "3. 必须包含具体数据（数量、金额、百分比、同比等；可基于公开行业趋势给出量级与区间，口径自洽）；\n"
    "4. 使用连贯的段落文字，不要使用列表和 Markdown 符号。\n"
    "本节内容要求：{instruction}"
)

EXTEND_PROMPT_TMPL = (
    "你在为《{title}》的小节「{heading}」续写。下面是已写好的正文：\n{body}\n"
    "要求：\n"
    "1. 紧接上文补充 120 汉字左右（100—180 之间）的新内容（更细的数据、案例或因果分析）；\n"
    "2. 只输出续写的新内容，不要复述已有正文，不要写小结或客套话；\n"
    "3. 仍须包含至少 1 个具体数据，使用连贯段落，不要列表和 Markdown 符号。"
)


def fail(msg):
    print(f"[失败] {msg}", file=sys.stderr)
    sys.exit(1)


def count_han(text):
    """统计汉字数（不含标点、数字、字母与空白）。"""
    return len(re.findall(r"[一-鿿]", text))


def chat_once(messages, label, api_key):
    """发起一次生成请求（带网络层重试），max_tokens 恒 <= MAX_TOKENS_CAP。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "thinking": {"type": "disabled"},  # 关闭思考，避免思考 token 挤占 max_tokens
        "max_tokens": SECTION_MAX_TOKENS,
        "temperature": 0.5,
    }
    if payload["max_tokens"] > MAX_TOKENS_CAP:
        fail(f"内部错误：单次请求 max_tokens={payload['max_tokens']} 超过网关硬上限 {MAX_TOKENS_CAP}，拒绝发送。")

    last_err = None
    for attempt in range(1, RETRY_TIMES + 2):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}（服务端错误，第 {attempt} 次尝试）"
                time.sleep(2)
                continue
            return resp
        except requests.RequestException as exc:
            last_err = f"网络异常 {exc!r}（第 {attempt} 次尝试）"
            time.sleep(2)
    fail(f"{label} 请求重试 {RETRY_TIMES} 次后仍失败，卡在：{last_err}")


def extract_content(resp, label):
    """从响应中取出正文文本；异常路径直接 fail 并说明卡点。"""
    if resp.status_code != 200:
        fail(f"{label} HTTP {resp.status_code}，响应体片段：{resp.text[:500]}")
    try:
        data = resp.json()
    except ValueError:
        fail(f"{label} 响应不是合法 JSON：{resp.text[:500]}")
    err = data.get("error")
    if err:
        fail(f"{label} 平台返回错误 code={err.get('code')} message={err.get('message')}")
    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    finish = choice.get("finish_reason")
    if finish == "length":
        # 预算内被截断：裁掉最后半个句子，保留完整部分并告警
        trimmed = re.sub(r"[^。！？；]*$", "", content).strip()
        print(f"[警告] {label} finish_reason=length"
              f"（max_tokens={SECTION_MAX_TOKENS} 内被截断），已裁掉不完整的句尾。",
              file=sys.stderr)
        content = trimmed
    elif finish not in ("stop", None):
        fail(f"{label} 异常结束 finish_reason={finish}"
             f"（sensitive=内容安全拦截，network_error=模型推理异常），content 长度 {len(content)}")
    if not content:
        fail(f"{label} 返回空正文（finish_reason={finish}），无法继续。")
    return content


def generate_section(heading, instruction, api_key):
    messages = [
        {"role": "system", "content": "你是资深汽车行业市场分析师，写作风格克制、数据驱动。"},
        {"role": "user", "content": SECTION_PROMPT_TMPL.format(
            title=TITLE, heading=heading, instruction=instruction)},
    ]
    return extract_content(chat_once(messages, f"小节「{heading}」", api_key),
                           f"小节「{heading}」")


def extend_section(heading, body, api_key):
    messages = [
        {"role": "system", "content": "你是资深汽车行业市场分析师，写作风格克制、数据驱动。"},
        {"role": "user", "content": EXTEND_PROMPT_TMPL.format(
            title=TITLE, heading=heading, body=body)},
    ]
    return extract_content(chat_once(messages, f"扩写小节「{heading}」", api_key),
                           f"扩写小节「{heading}」")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置，无法调用 API。请先执行 "
             "export ZHIPUAI_API_KEY=<你的 Key> 再运行 python3 main.py")

    parts = []
    requests_made = 0
    for idx, (heading, instruction) in enumerate(SECTIONS):
        if requests_made >= MAX_TOTAL_REQUESTS:
            break
        if idx >= CORE_SECTIONS and sum(count_han(b) for _, b in parts) >= TARGET_HAN:
            break  # 核心小节已齐且字数达标，补充小节无需再发起请求
        body = generate_section(heading, instruction, api_key)
        requests_made += 1
        parts.append((heading, body))
        print(f"[进度] 已生成小节「{heading}」（{count_han(body)} 汉字）", file=sys.stderr)

    # 字数不足时，循环对最短的小节续写扩写，直到达标或请求数用尽
    while (sum(count_han(b) for _, b in parts) < TARGET_HAN
           and requests_made < MAX_TOTAL_REQUESTS):
        heading, body = min(parts, key=lambda p: count_han(p[1]))
        extra = extend_section(heading, body, api_key)
        requests_made += 1
        parts[parts.index((heading, body))] = (heading, body + extra)
        print(f"[进度] 已扩写小节「{heading}」（新增 {count_han(extra)} 汉字）", file=sys.stderr)

    total_han = sum(count_han(b) for _, b in parts)
    if total_han < TARGET_HAN:
        fail(f"共 {requests_made} 次请求后正文仍只有 {total_han} 汉字（要求 ≥{TARGET_HAN}），"
             f"卡在：模型持续返回过短的内容，已达请求数上限 {MAX_TOTAL_REQUESTS}，拒绝输出半成品。")

    document = TITLE + "\n\n" + "\n\n".join(f"## {h}\n{b}" for h, b in parts)
    print(document)
    print("\n" + "=" * 46)
    print(f"正文汉字数（不含标点/数字，仅统计小节正文）：{total_han}（要求 ≥ {TARGET_HAN}）")
    print(f"全文字符数（含标题、小标题与标点）：{len(document.replace(chr(10), ''))}")
    print(f"共发起 {requests_made} 次请求，每次 max_tokens={SECTION_MAX_TOKENS}"
          f"（网关硬上限 {MAX_TOKENS_CAP}，全程未超）")


if __name__ == "__main__":
    main()
