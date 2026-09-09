#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py —— 用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报

- 端点：POST https://open.bigmodel.cn/api/paas/v4/chat/completions（标准 API）
- 模型：glm-5.3（同步端点不会静默换模型；回显 model 字段仍逐一核对）
- 针对接入手册实测陷阱的防御：
  1) 思考 token 计入 max_tokens（陷阱 13）：600 字简报思考链就要 2400+ token，
     预算不足时 finish_reason=length、正文被截断。本脚本初始预算 8192（远高于
     实测需要的 3000），一旦撞上 length 自动翻倍并调低 reasoning_effort 重试。
  2) 标准端点 glm-5.3 关不掉 thinking（陷阱 14）：因此不传 thinking，靠足量
     max_tokens + reasoning_effort=low 保证正文完整。
  3) 残缺内容绝不交付（补救表的要求）：截断 / 过短 / 结尾悬空 / 缺小标题，
     都会触发自动补救——续写拼接、扩写重写，最后还有"分段生成再拼接"兜底；
     全部校验通过后才打印，绝不会把半截东西交给用户。
- API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖 requests + 标准库。

用法：python3 main.py
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
ENV_KEY = "ZHIPUAI_API_KEY"

MIN_CHARS = 600        # 交付门槛：非空白字符数（含标点，即通常说的"字数"）
MIN_HEADINGS = 3       # 交付门槛：小标题个数
MIN_DATA_POINTS = 3    # 交付门槛：数字型具体数据出现处数
TARGET_CHARS = 900     # 提示词里要求的字数（高于门槛，留出余量）
INIT_MAX_TOKENS = 8192  # 首次请求输出预算（实测 600 字简报思考链 2400+ token，须 >= 3000）
MAX_TOKENS_CEILING = 131072

TOPIC = "2026 年中国新能源汽车出口"

SYSTEM_PROMPT = (
    "你是一名资深新能源汽车行业市场分析师，负责为公司管理层周报撰写市场简报。"
    "你的输出必须是结构完整、数据翔实、可直接放进周报的成稿，绝不输出半截内容。"
)

USER_PROMPT = f"""请围绕主题「{TOPIC}」撰写一份市场简报，严格要求如下：
1. 篇幅不少于 {TARGET_CHARS} 字（汉字为主，含标点），宁可写多不要写少；
2. 采用 Markdown 结构：第一行为总标题（# 开头），正文至少包含 4 个小标题（## 开头），
   建议依次覆盖：总体出口规模与增速、主要区域市场结构、竞争格局与头部企业表现、
   风险挑战与全年展望；
3. 每个小节都必须出现具体数据（如出口量、出口额、同比增速、市场份额、平均单价、
   主要目的地占比等，写成"数字+单位"的形式）；
4. 结构完整：开头有 2~3 句总体概述，结尾有小结段落收束全文，最后一句必须是完整句子；
5. 直接输出简报正文本身，不要输出任何解释、前言或"以下是简报"之类的客套话。"""

CONTINUE_PROMPT = (
    "你刚才的输出在中途断掉了。请从断点处无缝续写，补完全文剩余部分"
    "（不要重复已输出的内容），最后用一段完整的小结收束全文。只输出续写的部分。"
)

# 分段生成兜底：每个小节独立生成、独立校验，再拼接（补救表第 ③ 招）
SEGMENTED_SECTIONS = [
    (
        "总体出口规模与增速",
        "写 2026 年中国新能源汽车出口的总量与增速：出口量（万辆）、出口额（亿美元）、"
        "同比增速、在汽车整体出口中的占比等。不少于 260 字，至少 3 处具体数据。",
    ),
    (
        "主要区域市场结构",
        "写欧洲、东南亚、拉美、中东等主要目的地市场的格局与占比变化。"
        "不少于 260 字，至少 3 处具体数据。",
    ),
    (
        "竞争格局与头部企业表现",
        "写比亚迪、奇瑞、上汽、长城、特斯拉上海工厂等头部企业的出口量与份额变化。"
        "不少于 260 字，至少 3 处具体数据。",
    ),
    (
        "风险挑战与全年展望",
        "写欧盟反补贴税、海运运力、海外本地化建厂、汇率等挑战，以及对 2026 全年走势的预判。"
        "不少于 260 字，至少 3 处具体数据。",
    ),
]


class GenerationError(RuntimeError):
    """生成流程中无法就地修复的问题。"""


# ---------------------------------------------------------------- 文本度量

def count_chars(text):
    """返回 (非空白字符数, 其中汉字数)。非空白字符数即通常意义的"字数"。"""
    non_ws = len(re.sub(r"\s+", "", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return non_ws, cjk


_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*\S"
    r"|[一二三四五六七八九十]{1,3}[、.．:：]"
    r"|[（(][一二三四五六七八九十]{1,3}[)）]"
    r"|\d{1,2}[、.．]\s*\S)",
    re.M,
)


def count_headings(text):
    """统计小标题行：# 开头、"一、"、"（一）"、"1." 等形式都算。"""
    return len(_HEADING_RE.findall(text))


def count_numbers(text):
    """统计数字型数据出现处数（整数或小数）。"""
    return len(re.findall(r"\d+(?:\.\d+)?", text))


_CLOSING_CHARS = set("。！？；：）】》」』”’!?;:)…％%*#\"'")


def ends_complete(text):
    """结尾是否收束：最后一个可见字符应是句读/括号等收尾符，而不是逗号、破折号或半个词。"""
    t = text.rstrip()
    return bool(t) and t[-1] in _CLOSING_CHARS


def text_stats(text):
    total, cjk = count_chars(text)
    return {
        "total": total,
        "cjk": cjk,
        "headings": count_headings(text),
        "numbers": count_numbers(text),
        "ends_ok": ends_complete(text),
    }


def validate(text):
    """交付前校验。返回 (问题列表, 非空白字符数, 汉字数)；问题列表为空即合格。"""
    st = text_stats(text)
    problems = []
    if st["total"] < MIN_CHARS:
        problems.append(f"字数不足（{st['total']} < {MIN_CHARS}）")
    if st["headings"] < MIN_HEADINGS:
        problems.append(f"小标题不足（{st['headings']} < {MIN_HEADINGS}）")
    if st["numbers"] < MIN_DATA_POINTS:
        problems.append(f"具体数据不足（{st['numbers']} < {MIN_DATA_POINTS}）")
    if not st["ends_ok"]:
        problems.append("结尾未收束（疑似中途断掉）")
    return problems, st["total"], st["cjk"]


def _strip_fence(text):
    """剥掉模型可能包裹的整体 ``` 围栏与 <think> 标签。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
    return text.strip()


def merge_without_overlap(a, b, window=40):
    """拼接正文 a 与续写 b；若 b 开头重复了 a 的结尾则去掉重复段。"""
    w = min(window, len(a), len(b))
    for k in range(w, 0, -1):
        if a.endswith(b[:k]):
            return a + b[k:]
    return a + ("\n" if b and not b[0].isspace() and not b.startswith("#") else "") + b


def _better(a, b):
    """两版文稿里挑校验问题更少的一版；问题数相同则挑字数更多的。"""
    pa, ta, _ = validate(a)
    pb, tb, _ = validate(b)
    return b if (len(pb), -tb) < (len(pa), -ta) else a


# ---------------------------------------------------------------- API 调用

API_KEY = os.environ.get(ENV_KEY, "").strip()


def _check_model_echo(echoed, tag):
    """核对回显 model（陷阱 2/3：异步端点会静默换模型）。同步端点正常应原样回显；
    版本号后缀差异（如 glm-5.3-26xxxx）只记日志；换成了别的模型则计费与能力都变了，
    必须报警停下，不能装作没看见。"""
    if not echoed:
        return
    e = echoed.strip().lower()
    if e == MODEL or e.startswith(MODEL + "-"):
        return
    raise GenerationError(
        f"{tag}：服务端实际执行的是 {echoed}（请求的是 {MODEL}），"
        "计费系数与模型能力都已变化，停止交付。"
    )


def _chat_once(messages, max_tokens, reasoning_effort=None):
    """单次同步调用（带 HTTP 层重试）。返回 (content, finish_reason, 回显model, usage)。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=(15, 300))
        except requests.RequestException as exc:
            last_err = f"网络异常：{exc}"
            time.sleep(2 * attempt)
            continue
        if resp.status_code in (401, 403):
            raise GenerationError(
                f"鉴权失败（HTTP {resp.status_code}）：请检查环境变量 {ENV_KEY} 是否为有效的标准 API Key。"
                f"返回内容：{resp.text[:200]}"
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"HTTP {resp.status_code}（第 {attempt} 次）"
            time.sleep(3 * attempt)
            continue
        if resp.status_code != 200:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text[:200])
            except ValueError:
                msg = resp.text[:200]
            raise GenerationError(f"请求被拒绝（HTTP {resp.status_code}）：{msg}")
        try:
            data = resp.json()
        except ValueError as exc:
            last_err = f"响应不是合法 JSON：{exc}"
            time.sleep(2)
            continue
        # 防御：个别子系统 HTTP 200 也带 error 体
        if data.get("error") and not data.get("choices"):
            err = data["error"]
            raise GenerationError(f"API 返回错误：{err.get('code')} {err.get('message')}")
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        return content, choice.get("finish_reason"), data.get("model", ""), data.get("usage") or {}
    raise GenerationError(f"连续 3 次网络/服务端失败：{last_err}")


def _chat_until_complete(messages, tag, log):
    """拿到"正常结束且非空"的正文为止：
    - 撞上 length（思考 token 吃光预算，陷阱 13）→ 翻倍 max_tokens 并降思考强度重试；
    - 敏感/推理异常 → 等待后重试；
    - 其余异常 finish_reason → 报错交由上层兜底。"""
    budget, effort = INIT_MAX_TOKENS, None
    for _ in range(4):
        content, finish, echoed, _usage = _chat_once(messages, budget, effort)
        _check_model_echo(echoed, tag)
        log(f"{tag}：finish_reason={finish}，max_tokens={budget}，"
            f"正文 {count_chars(content)[0]} 字")
        if finish == "length" or not content.strip():
            # 预算翻倍；glm-5.3 标准端点关不掉 thinking，改用 reasoning_effort=low 省思考 token
            if budget >= MAX_TOKENS_CEILING:
                break
            budget = min(budget * 2, MAX_TOKENS_CEILING)
            effort = "low"
            continue
        if finish in ("sensitive", "network_error", "model_context_window_exceeded"):
            time.sleep(5)
            continue
        if finish != "stop":
            raise GenerationError(f"{tag}：异常 finish_reason={finish}")
        return _strip_fence(content)
    raise GenerationError(f"{tag}：多轮调整预算后仍拿不到完整正文，放弃该路径")


# ---------------------------------------------------------------- 生成策略

def _base_messages(user_prompt):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _continue_repair(messages, partial, log, round_no):
    """结尾悬空：把半截稿作为 assistant 历史，让模型从断点续写，再去重拼接。"""
    repair_msgs = messages + [
        {"role": "assistant", "content": partial},
        {"role": "user", "content": CONTINUE_PROMPT},
    ]
    cont = _chat_until_complete(repair_msgs, f"续写修复#{round_no}", log)
    return merge_without_overlap(partial, cont)


def _expand_repair(messages, current, log, round_no):
    """未过校验（过短/缺小标题/缺数据）：要求输出修订后的完整全文，两版取优。"""
    total, _ = count_chars(current)
    expand_msgs = messages + [
        {"role": "assistant", "content": current},
        {"role": "user", "content": (
            f"你上一版简报未达交付标准（当前约 {total} 字）。请输出修订后的【完整全文】：\n"
            f"1) 不少于 {TARGET_CHARS} 字；\n"
            f"2) 第 1 行为 # 总标题，正文至少 {MIN_HEADINGS + 1} 个 ## 小标题；\n"
            f"3) 每个小节都含具体数据（数字+单位）；\n"
            "4) 结尾用完整的小结段落收束。直接输出全文，不要任何解释。"
        )},
    ]
    revised = _chat_until_complete(expand_msgs, f"扩写修复#{round_no}", log)
    return _better(current, revised)


def generate_whole(log):
    """整篇生成 + 就地修复（截断已在 _chat_until_complete 内消化）。"""
    messages = _base_messages(USER_PROMPT)
    content = _chat_until_complete(messages, "整篇生成", log)

    # 修复一：结尾悬空（finish=stop 但明显断在半句）→ 续写拼接
    round_no = 0
    while not ends_complete(content) and round_no < 2:
        round_no += 1
        log("检测到结尾未收束，发起续写修复")
        content = _continue_repair(messages, content, log, round_no)

    # 修复二：字数/小标题/数据不达标 → 扩写重写
    round_no = 0
    while True:
        problems, _total, _cjk = validate(content)
        if not problems or round_no >= 2:
            break
        round_no += 1
        log(f"校验未通过（{'；'.join(problems)}），发起扩写修复")
        content = _expand_repair(messages, content, log, round_no)

    problems, _total, _cjk = validate(content)
    if problems:
        raise GenerationError("整篇生成修复后仍未达标：" + "；".join(problems))
    return content


def generate_segmented(log):
    """兜底策略：分段生成再拼接（补救表第 ③ 招）。每个小节独立调用、独立校验，
    单节预算充足不容易截断，拼起来的全文结构由代码保证。"""
    parts = []
    cn = "一二三四五"
    for idx, (title, requirement) in enumerate(SEGMENTED_SECTIONS, 1):
        if idx == 1:
            prompt = (
                f"为周报撰写关于「{TOPIC}」的市场简报的第一部分：先输出 1 行总标题"
                f"（# 开头）和 2~3 句总体导语，然后输出小节「## {cn[idx - 1]}、{title}」。"
                f"要求：{requirement}只输出这一部分，不要写其他小节。"
            )
        else:
            prompt = (
                f"继续写同一份简报的小节「## {cn[idx - 1]}、{title}」。"
                f"要求：{requirement}只输出这一小节（以小标题行开头），不要重复前面的小节。"
            )
        sec = _chat_until_complete(_base_messages(prompt), f"分段#{idx}", log)
        # 小节级校验：长度、数据、结尾都要过关，否则不拼
        if count_chars(sec)[0] < 150 or count_numbers(sec) < 1 or not ends_complete(sec):
            raise GenerationError(f"分段#{idx}（{title}）内容不达标，放弃拼接")
        parts.append(sec)

    draft = "\n\n".join(parts)
    tail_prompt = (
        f"以下是已写好的简报：\n\n{draft}\n\n"
        f"请为它补一个小节「## {cn[len(SEGMENTED_SECTIONS)]}、结语」：2~3 句收束全文，"
        "至少含 1 处数据，以完整句结尾。只输出该小节。"
    )
    tail = _chat_until_complete(_base_messages(tail_prompt), "结语", log)
    if count_numbers(tail) < 1 or not ends_complete(tail):
        raise GenerationError("结语小节不达标，放弃拼接")
    return draft + "\n\n" + tail


# ---------------------------------------------------------------- 主流程

def main():
    def log(msg):
        print(f"[生成日志] {msg}", flush=True)

    global API_KEY
    API_KEY = os.environ.get(ENV_KEY, "").strip()
    if not API_KEY:
        print(
            f"[错误] 未设置环境变量 {ENV_KEY}，无法调用智谱 API。\n"
            f"请先执行：export {ENV_KEY}=\"你的 API Key\"",
            file=sys.stderr,
        )
        sys.exit(1)

    mode = "一次性生成"
    try:
        try:
            briefing = generate_whole(log)
        except GenerationError as exc:
            log(f"一次性生成未能交付（{exc}），转入分段生成兜底")
            briefing = generate_segmented(log)
            mode = "分段生成兜底"

        # 交付前的最终闸门：无论哪条路径产出，必须全部校验通过才放行
        problems, total, cjk = validate(briefing)
        if problems:
            raise GenerationError("最终校验未通过：" + "；".join(problems))
    except GenerationError as exc:
        print(
            f"\n[错误] {exc}\n未能产出合格简报——按约定不交付任何半成品，"
            "请检查网络 / API Key / 平台状态后重试。",
            file=sys.stderr,
        )
        sys.exit(2)

    st = text_stats(briefing)
    line = "=" * 64
    print()
    print(line)
    print(f"《{TOPIC}》市场简报 —— 智谱 GLM（{MODEL}）生成")
    print(line)
    print(briefing)
    print(line)
    print("交付校验结果：")
    print(f"  1) 字数：{st['total']} 字（其中汉字 {st['cjk']} 字），要求 ≥{MIN_CHARS} 字 —— "
          f"{'✅ 达标' if st['total'] >= MIN_CHARS else '❌ 未达标'}")
    print(f"  2) 小标题：{st['headings']} 个，要求 ≥{MIN_HEADINGS} 个 —— "
          f"{'✅ 达标' if st['headings'] >= MIN_HEADINGS else '❌ 未达标'}")
    print(f"  3) 具体数据：{st['numbers']} 处数字，要求 ≥{MIN_DATA_POINTS} 处 —— "
          f"{'✅ 达标' if st['numbers'] >= MIN_DATA_POINTS else '❌ 未达标'}")
    print(f"  4) 完整性：生成方式「{mode}」，各次调用均 finish_reason=stop（未被 max_tokens 截断），"
          f"结尾完整收束 —— {'✅ 完整' if st['ends_ok'] else '❌ 存疑'}")
    print()
    print(f"结论：简报内容完整、无截断，字数 {st['total']} ≥ {MIN_CHARS} 达标，可直接放入周报。")
    print("（提示：文中数据由模型生成，正式引用前请复核关键数字。）")
    print(line)


if __name__ == "__main__":
    main()
