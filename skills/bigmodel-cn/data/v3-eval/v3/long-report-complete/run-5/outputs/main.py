#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报。

用法：
    export ZHIPUAI_API_KEY=<你的 Key>
    python3 main.py

产出：一篇不少于 600 字、带小标题和具体数据的完整简报——打印全文，
并给出字数 / 完整性 / 结构的校验结论。

针对智谱平台实测坑位的处理（见 bigmodel-cn 技能包 SKILL.md）：
- 思考 token 计入 max_tokens（坑 #13）：600 字简报的思考链就可能吃掉
  2400+ token，所以首次调用就把预算给足 8192，而不是按正文长度估算；
- glm-5.3 在标准端点无法关闭 thinking，传 disabled 会报 1210（坑 #14），
  因此省 token 的手段用 reasoning_effort="low"，不碰 thinking 开关；
- 读回响应里的 model 字段核对（坑 #2/#3）：同步端点正常不换模型，
  一旦回显换成别的模型家族，计费与能力口径都变了，立即停下报警；
- 撞上 finish_reason=="length" 绝不把半截内容交给用户（补救表第 1 行），
  按阶梯自动补救：预算翻倍重试 → 降低思考强度 → 截断处续写拼接；
  字数不足时扩写。全部手段用尽仍不达标才报错退出，且不输出残稿。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

MIN_CHARS = 600      # 用户硬性要求：不少于 600 字
TARGET_CHARS = 800   # 下发给模型的目标字数，给硬指标留出余量
MIN_HEADINGS = 3     # 至少 3 个小标题才算结构达标
MIN_NUMBERS = 6      # 至少 6 处数字才算"有具体数据"

HTTP_TIMEOUT = (10, 300)   # 思考模型出活慢：连接 10s、读取 300s
MAX_NETWORK_RETRIES = 3    # 网络异常 / 限流 / 5xx 的重试次数

SYSTEM_PROMPT = "你是一名资深汽车行业市场分析师，为公司管理层周报撰写市场简报，文字专业、数据具体、结论明确。"


class GenerationError(RuntimeError):
    """多级补救后仍拿不到达标简报。携带过程日志，便于排查。"""

    def __init__(self, message, notes):
        super().__init__(message)
        self.notes = notes


# ---------------------------------------------------------------- 校验工具

def count_chars(text):
    """字数：非空白字符数（含标点，与常见编辑器的"字数"口径一致）。"""
    return sum(1 for c in text if not c.isspace())


def count_hanzi(text):
    return len(re.findall(r"[一-鿿]", text))


def count_headings(text):
    return len(re.findall(r"^#{1,3}\s+\S", text, re.MULTILINE))


def count_numbers(text):
    return len(re.findall(r"\d+(?:\.\d+)?", text))


def ends_cleanly(text):
    """结尾完整性启发式：不能停在小标题上，且末字符应是句读/收束符号。"""
    stripped = text.rstrip()
    if not stripped:
        return False
    last_line = stripped.splitlines()[-1].strip()
    if last_line.startswith("#"):
        return False  # 最后一行是小标题 → 正文还没写出来
    return stripped[-1] in "。！？；：）)”》】…\"”"


def validate(text):
    """返回问题列表；空列表 = 达标可交付。"""
    problems = []
    if count_chars(text) < MIN_CHARS:
        problems.append(f"字数不足（{count_chars(text)} 字 < {MIN_CHARS} 字）")
    if count_headings(text) < MIN_HEADINGS:
        problems.append(f"小标题不足（{count_headings(text)} 个 < {MIN_HEADINGS} 个）")
    if count_numbers(text) < MIN_NUMBERS:
        problems.append(f"具体数据过少（仅 {count_numbers(text)} 处数字 < {MIN_NUMBERS} 处）")
    if not ends_cleanly(text):
        problems.append("结尾不完整（未以完整句收束，或停在小标题上）")
    return problems


# ---------------------------------------------------------------- API 调用

def check_model_echo(echo):
    """坑 #2/#3：读回 model 字段核对。仅版本号/日期后缀差异放行；换成别的模型家族则停下报警。"""
    strip_suffix = lambda name: re.sub(r"-\d{6,}$", "", (name or "").lower())
    if strip_suffix(echo) != strip_suffix(MODEL):
        raise RuntimeError(
            f"响应回显 model={echo!r} 与请求的 {MODEL!r} 不一致——"
            "实际运行的模型被更换，计费系数与能力都变了，请先核实再重跑"
        )


def call_glm(api_key, messages, max_tokens, reasoning_effort=None):
    """调用同步 chat/completions。返回 (content, finish_reason, usage, model_echo)。

    只重试网络异常、429 和 5xx；业务错误（4xx 带 code/message）直接抛出，
    带上平台错误码方便按 SKILL.md 排查。
    """
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_NETWORK_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}"
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                err = body.get("error") or {}
                raise RuntimeError(
                    f"接口返回 HTTP {resp.status_code}（code={err.get('code', '')}）："
                    f"{err.get('message') or str(body)[:200]}"
                )
            data = resp.json()
            if data.get("error"):  # HTTP 200 却带错误体的兜底
                err = data["error"]
                raise RuntimeError(f"code={err.get('code')} message={err.get('message')}")
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"响应缺少 choices：{str(data)[:200]}")
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            return content, choices[0].get("finish_reason"), data.get("usage", {}), data.get("model", MODEL)
        except requests.RequestException as exc:
            last_err = f"网络异常: {exc}"
            time.sleep(2 ** attempt)
    raise RuntimeError(f"请求连续 {MAX_NETWORK_RETRIES} 次失败（{last_err}）")


# ---------------------------------------------------------------- 提示词

def briefing_request():
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            "请撰写一篇主题为《2026 年中国新能源汽车出口市场简报》的完整市场简报，供管理层周报直接引用。\n"
            "硬性要求：\n"
            f"1. 篇幅：正文不少于 {TARGET_CHARS} 字（按含标点的字符数计算），宁多勿少。\n"
            "2. 结构：先用一两句导语概括，再用至少 4 个 Markdown 二级小标题（形如「## 一、整体出口规模与增速」）分节；"
            "建议覆盖：整体出口规模与增速、区域市场格局、头部企业与车型表现、挑战与风险、趋势展望。\n"
            "3. 数据：每一节至少给出 1~2 个具体数据（出口量、同比增速、出口金额、平均单价、市场份额、"
            "目的地国家占比等），可基于 2024—2025 年公开行业趋势对 2026 年给出合理估计，数据口径保持自洽。\n"
            "4. 完整性：必须有收尾的展望小节，全文语义完整收束，绝不能中途截断。\n"
            "5. 输出：只输出简报正文本身，不要开场白、不要解释、不要代码围栏。"
        )},
    ]


def expand(api_key, draft, notes):
    """finish_reason=stop 但字数不足时，带着原稿要求扩写。返回 (content, finish_reason)。"""
    messages = briefing_request() + [
        {"role": "assistant", "content": draft},
        {"role": "user", "content": (
            f"你这一稿按含标点字符数只有 {count_chars(draft)} 字，未达到 {TARGET_CHARS} 字的硬性要求。"
            "请保留原有小标题结构与数据，逐节扩写实写（补充数据、案例与分析），"
            f"扩写到不少于 {TARGET_CHARS} 字，并以完整的展望段收尾。直接输出扩写后的完整简报全文。"
        )},
    ]
    content, finish, usage, echo = call_glm(api_key, messages, 8192)
    check_model_echo(echo)
    notes.append(
        f"扩写：finish_reason={finish}，正文 {count_chars(content)} 字，"
        f"completion_tokens={usage.get('completion_tokens', '?')}"
    )
    return content, finish


def merge_seamless(prefix, continuation):
    """拼接续写内容；若模型重复了一小段前文，把重叠部分从续写里削掉。"""
    cont = continuation.strip("\n")
    if not cont:
        return prefix
    for overlap in range(min(len(prefix), len(cont), 120), 9, -1):
        if prefix.endswith(cont[:overlap]):
            return prefix + cont[overlap:]
    return prefix + ("\n" if not prefix.endswith("\n") else "") + cont


def continue_until_done(api_key, truncated, notes, max_rounds=3):
    """补救手段③：拿着截断稿从断点续写，直到 finish_reason=stop 且结尾完整。"""
    text = truncated
    finish = "length"
    for round_no in range(1, max_rounds + 1):
        tail = text[-800:]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "下面是一篇尚未写完的市场简报的末尾部分。请从截断处无缝续写，把剩余小节写完，"
                "并以完整的「趋势展望」段收尾。不要重复前文任何一个字，不要重新加总标题，"
                "直接输出续写部分。\n\n"
                f"---前文末尾---\n{tail}\n---前文结束---"
            )},
        ]
        # 续写阶段用 low 档思考：剩余篇幅不长，把预算尽量留给正文（坑 #13/#14）
        cont, finish, usage, echo = call_glm(api_key, messages, 8192, reasoning_effort="low")
        check_model_echo(echo)
        notes.append(
            f"续写第 {round_no} 轮：finish_reason={finish}，增补 {count_chars(cont)} 字，"
            f"completion_tokens={usage.get('completion_tokens', '?')}"
        )
        if not cont.strip():
            break
        text = merge_seamless(text, cont)
        if finish == "stop" and ends_cleanly(text):
            break
    return text


# ---------------------------------------------------------------- 生成主流程

def generate_briefing(api_key):
    """生成并通过全部校验才返回 (简报全文, 过程日志)；否则抛 GenerationError。"""
    notes = []
    best, best_truncated = "", False  # 迄今最长的一版，留给续写补救

    # 补救阶梯（SKILL.md 补救表第 1 行的顺序）：
    # 首轮预算给足 → ① 撞 length 就翻倍 → ② glm-5.3 关不掉思考，改用 low 档压缩思考消耗
    ladder = [
        ("首轮生成（max_tokens=8192，思考 token 计入预算，直接给足）", 8192, None),
        ("截断补救①：max_tokens 翻倍到 16384 重试", 16384, None),
        ("截断补救②：reasoning_effort=low 压缩思考消耗", 16384, "low"),
    ]

    for desc, budget, effort in ladder:
        content, finish, usage, echo = call_glm(api_key, briefing_request(), budget, effort)
        check_model_echo(echo)
        notes.append(
            f"{desc}：finish_reason={finish}，正文 {count_chars(content)} 字，"
            f"completion_tokens={usage.get('completion_tokens', '?')}"
        )
        if count_chars(content) > count_chars(best):
            best, best_truncated = content, finish != "stop"
        if finish != "stop" or not content.strip():
            # length=被截断；sensitive/network_error=被拦或推理异常；空正文同治 → 升级下一档
            continue
        problems = validate(content)
        if not problems:
            return content, notes
        notes.append("  校验未过：" + "；".join(problems))
        if any("字数不足" in p for p in problems):
            expanded, exp_finish = expand(api_key, content, notes)
            if count_chars(expanded) > count_chars(best):
                best, best_truncated = expanded, exp_finish != "stop"
            if exp_finish == "stop" and not validate(expanded):
                return expanded, notes
        # 其余情况（结构/结尾问题）→ 换档重新生成

    # 阶梯用尽：手里若有一份够长的截断稿，走补救手段③续写拼接
    if best.strip() and best_truncated:
        stitched = continue_until_done(api_key, best, notes)
        if not validate(stitched):
            return stitched, notes
        notes.append("  续写后校验仍未过：" + "；".join(validate(stitched)))

    raise GenerationError(
        "多级补救（预算翻倍 / 降低思考强度 / 截断续写 / 扩写）后仍未得到完整且达标的简报，"
        "为避免把残缺内容交给用户，本次不输出正文。最长一版约 "
        f"{count_chars(best)} 字。请检查网络与 Key 后重试。",
        notes,
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行 export ZHIPUAI_API_KEY=<你的 Key> 再运行。", file=sys.stderr)
        sys.exit(1)

    print(f"正在调用智谱 GLM（{MODEL}）生成简报，思考模型耗时较长，请稍候……", flush=True)
    try:
        briefing, notes = generate_briefing(api_key)
    except GenerationError as exc:
        print(f"\n生成失败：{exc}\n", file=sys.stderr)
        print("过程日志（用于排查）：", file=sys.stderr)
        for line in exc.notes:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"\n调用失败：{exc}", file=sys.stderr)
        sys.exit(1)

    # ---- 交付：全文 + 明确的达标确认 ----
    chars, hanzi = count_chars(briefing), count_hanzi(briefing)
    headings, numbers = count_headings(briefing), count_numbers(briefing)
    complete = ends_cleanly(briefing)
    passed = chars >= MIN_CHARS and headings >= MIN_HEADINGS and numbers >= MIN_NUMBERS and complete

    print("\n" + "=" * 64)
    print(briefing.strip())
    print("=" * 64)
    print("\n校验结论：")
    print(f"  - 字数：{chars} 字（含标点、不含空白；其中汉字 {hanzi} 个）"
          f"—— 要求 ≥{MIN_CHARS} 字：{'✅ 达标' if chars >= MIN_CHARS else '❌ 不达标'}")
    print(f"  - 结构：{headings} 个小标题 —— 要求 ≥{MIN_HEADINGS} 个："
          f"{'✅ 达标' if headings >= MIN_HEADINGS else '❌ 不达标'}")
    print(f"  - 数据：正文含 {numbers} 处具体数字 —— 要求 ≥{MIN_NUMBERS} 处："
          f"{'✅ 达标' if numbers >= MIN_NUMBERS else '❌ 不达标'}")
    print(f"  - 完整性：{'✅ 已以完整句收束，无中途截断' if complete else '❌ 结尾可疑'}")
    if passed:
        print(f"\n✅ 简报完整、字数达标，可直接放入周报。")
    else:
        print("\n❌ 校验未全部通过，请勿直接使用。", file=sys.stderr)
        sys.exit(1)

    print("\n生成过程：")
    for line in notes:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
