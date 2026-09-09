#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱 GLM（glm-5.3）生成《2026 年中国新能源汽车出口市场简报》。

硬性要求：正文不少于 600 字、有小标题、有具体数据、内容完整不截断。

残缺内容的兜底处理（拿到半截绝不直接交付）：
- finish_reason == "length"（达到 max_tokens 被截断，思考 token 也计入该预算）时，
  自动把已生成内容拼回对话并要求"从中断处续写"，循环直到自然收尾；
- 内容过短 / 缺小标题 / 缺数据 / 结尾可疑时，带着具体问题反馈自动重新生成；
- 以上补救全部失败则报错退出（exit 1），不打印任何残缺简报。

依赖：仅 requests。用法：ZHIPUAI_API_KEY=你的Key python3 main.py
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
MIN_CHARS = 600        # 交付的硬性字数下限
TARGET_CHARS = 900     # 提示词里要求的字数（比下限留足冗余）
MAX_TOKENS = 8192      # glm-5.3 上限 131072；思考 token 计入 max_tokens，预算给足
TIMEOUT = 300
MAX_ATTEMPTS = 4       # 整体重生成次数上限
MAX_CONT_ROUNDS = 4    # 单次生成内的续写轮数上限

# 简报正常收尾时最后一个字符应落在这些"句读"里
TERMINALS = tuple("。！？；：”』」）)")


# ---------------------------------------------------------------- 校验工具

def count_chars(text):
    """正文字数：去掉 Markdown 标记与全部空白后的字符数（≈ Word 的"字符数(不计空格)"）。"""
    body = re.sub(r"[#*`>]+", "", text)
    body = re.sub(r"^\s*[-+]\s+", "", body, flags=re.M)  # 去掉列表符
    body = re.sub(r"\s+", "", body)
    return len(body)


def count_cjk(text):
    """纯汉字数，作为更严的参考口径。"""
    return len(re.findall(r"[一-鿿]", text))


def count_subheadings(text):
    """小标题个数：Markdown # 标题或"一、二、"式中文序号标题，取两者较大值。"""
    md = len(re.findall(r"^\s*#{1,6}\s+\S", text, re.M))
    cn = len(re.findall(r"^\s*[一二三四五六七八九十]+\s*[、.．]\s*\S", text, re.M))
    return max(md, cn)


def count_numbers(text):
    """文中具体数据（数字）出现次数。"""
    return len(re.findall(r"\d+(?:\.\d+)?", text))


def looks_finished(text):
    """结尾是否是自然句读（而非截断在半句/半个表格中间）。"""
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in TERMINALS


def validate(text, finish_reason):
    """返回问题列表；为空即视为合格、完整、可交付。"""
    problems = []
    if count_chars(text) < MIN_CHARS:
        problems.append(f"字数不足（{count_chars(text)} 字 < {MIN_CHARS} 字）")
    if count_subheadings(text) < 3:
        problems.append("小标题不足 3 个")
    if count_numbers(text) < 5:
        problems.append("具体数据（数字）少于 5 处")
    if finish_reason != "stop":
        problems.append(f"finish_reason={finish_reason}，模型未自然结束")
    elif not looks_finished(text):
        problems.append("结尾不是自然句读，疑似被截断")
    return problems


# ---------------------------------------------------------------- API 调用

def call_chat(api_key, messages, max_tokens=MAX_TOKENS):
    """调用同步对话补全，返回 (content, finish_reason)。瞬时错误自动重试 3 次。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        # glm-5.3 在标准端点思考强制开启且思考 token 计入 max_tokens，
        # 调低推理强度（可选 low/high/max），把预算尽量留给正文。
        "reasoning_effort": "low",
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None
    for i in range(3):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code != 200:
                if resp.status_code in (429, 500, 502, 503, 504) and i < 2:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(2 ** (i + 1))
                    continue
                raise RuntimeError(f"API 返回 HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"API 业务错误: {data['error']}")
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            return content, choice.get("finish_reason", "")
        except requests.RequestException as e:
            last_err = str(e)
            if i == 2:
                break
            time.sleep(2 ** (i + 1))
    raise RuntimeError(f"请求智谱 API 失败（已重试）: {last_err}")


# ---------------------------------------------------------------- 生成主流程

BASE_PROMPT = f"""请撰写一篇《2026 年中国新能源汽车出口市场简报》，硬性要求：
1. 正文不少于 {TARGET_CHARS} 字（硬性要求，宁可写长也不要写短）；
2. 用小标题分节（如"## 一、整体出口规模"），至少 4 个小节；
3. 每个小节都要有具体数据支撑（出口量、同比增速、出口金额、主要目的地市场、
   市占率、头部车企表现等），数字要具体，不要泛泛而谈；
4. 结构完整：开头有总体概述，中间分主题展开，结尾有"展望与风险"收束段落，
   全文最后一句必须是完整句子；
5. 直接输出简报正文本身，不要输出任何额外解释或客套话。"""

SYSTEM_PROMPT = (
    "你是一名新能源汽车行业的资深市场分析师，擅长撰写数据翔实、结构清晰的行业简报。"
    "写作时必须一次性输出完整全文，务必写到自然收尾，不允许中途停止。"
)


def generate_report(api_key):
    """生成并校验简报，只有完全合格才返回；残缺内容在内部消化掉。"""
    feedback = ""
    max_tokens = MAX_TOKENS

    for attempt in range(1, MAX_ATTEMPTS + 1):
        user_prompt = BASE_PROMPT
        if feedback:
            user_prompt += "\n\n你上一次的输出存在如下问题，请重新完整输出修正后的全文：\n" + feedback
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            content, finish = call_chat(api_key, msgs, max_tokens)
        except RuntimeError as e:
            print(f"[尝试 {attempt}/{MAX_ATTEMPTS}] 调用失败：{e}", file=sys.stderr)
            time.sleep(2)
            continue

        if finish in ("sensitive", "network_error"):
            print(f"[尝试 {attempt}/{MAX_ATTEMPTS}] finish_reason={finish}，重试……", file=sys.stderr)
            time.sleep(2)
            continue

        # —— 截断自愈：finish_reason == "length" 或结尾不是自然句读时，自动续写拼接 ——
        rounds = 0
        while (finish == "length" or (content.strip() and not looks_finished(content))) \
                and rounds < MAX_CONT_ROUNDS:
            rounds += 1
            print(f"[尝试 {attempt}] 输出被截断（finish_reason={finish}），"
                  f"自动续写第 {rounds} 轮……", file=sys.stderr)
            cont_msgs = list(msgs)
            if content.strip():
                cont_msgs.append({"role": "assistant", "content": content})
            cont_msgs.append({
                "role": "user",
                "content": "你刚才的输出因长度限制在中途被截断了。请从被截断的位置继续往下写，"
                           "不要重复已写内容、不要重新开头，直接续写，直到简报完整收尾。",
            })
            try:
                more, finish = call_chat(api_key, cont_msgs, max_tokens)
            except RuntimeError as e:
                print(f"[尝试 {attempt}] 续写调用失败：{e}", file=sys.stderr)
                break
            if not more.strip():
                break
            content = content + ("\n" if not content.endswith("\n") else "") + more

        problems = validate(content, finish)
        if not problems:
            return content.strip()
        feedback = "；".join(problems)
        print(f"[尝试 {attempt}/{MAX_ATTEMPTS}] 内容未达标（{feedback}），带反馈重试……",
              file=sys.stderr)
        max_tokens = min(max_tokens * 2, 32768)

    raise RuntimeError(
        f"连续 {MAX_ATTEMPTS} 次仍未产出合格的完整简报，最后问题：{feedback or '调用反复失败'}。"
        "为避免交付残缺内容，本次不输出简报。"
    )


# ---------------------------------------------------------------- 入口

def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 "
              "export ZHIPUAI_API_KEY=<你的Key> 再运行本脚本。", file=sys.stderr)
        sys.exit(1)

    report = generate_report(api_key)

    chars = count_chars(report)
    cjk = count_cjk(report)
    subs = count_subheadings(report)
    nums = count_numbers(report)

    # 双保险：理论上 generate_report 返回的必然达标，这里再核一遍
    if chars < MIN_CHARS or subs < 3 or nums < 5 or not looks_finished(report):
        print("错误：终检未通过，拒绝输出可能残缺的简报。", file=sys.stderr)
        sys.exit(1)

    line = "=" * 66
    print(line)
    print(report)
    print(line)
    print()
    print("—— 交付确认 ——")
    print(f"✅ 字数达标：正文 {chars} 字 ≥ 要求的 {MIN_CHARS} 字"
          f"（口径：去除空白与 Markdown 标记后的字符数，其中汉字 {cjk} 个）")
    print(f"✅ 内容完整：模型自然收尾（finish_reason=stop、末尾为完整句读），未发生截断；"
          f"全文含 {subs} 个小标题、{nums} 处具体数据，结构完整，可直接进周报")


if __name__ == "__main__":
    main()
