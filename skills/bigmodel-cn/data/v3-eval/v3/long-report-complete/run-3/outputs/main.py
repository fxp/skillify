#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱 GLM 生成一份不少于 600 字、结构完整的周报级市场简报。
主题：2026 年中国新能源汽车出口。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

设计要点（对应 bigmodel-cn 技能包实测踩坑记录）：
  1. 思考 token 计入 max_tokens：600 字简报的思考链就要 2400+ token，预算给小了会
     finish_reason=length、正文截断甚至为空。这里 max_tokens 起步 8192，拿到空正文
     且 finish=length 时自动翻倍重试（上限 32768）。
  2. glm-5.3 在标准端点强制开启思考（传 thinking:disabled 会报 1210），因此不传
     thinking，改用 reasoning_effort=low 降低思考开销（官方文档：glm-5.3 仅接受
     max/high/low）。
  3. 判"是否截断"看 finish_reason（length）+ 结尾字符启发式，不单看空串。
  4. 撞上截断不报错退出：自动"从中断处续写并拼接"，直到 finish_reason=stop 且
     收尾完整；字数/小标题/数据不达标则追加式扩写。只把校验通过的完整成稿交给用户。
  5. 同步端点读回响应 model 字段核对（异步端点会静默换模型，同步不会，仍留一道保险）。
"""

import os
import re
import sys
import time

import requests

# ---------------------------------------------------------------- 基本配置

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"  # 标准 API 端点
MODEL = "glm-5.3"
REASONING_EFFORT = "low"   # glm-5.3 标准端点思考强制开启，用 low 控制思考强度
INITIAL_MAX_TOKENS = 8192  # 思考 token 计入 max_tokens，600 字简报需 3000+，给足余量
MAX_TOKENS_CAP = 32768     # 空正文（预算被思考吃光）时的翻倍上限
HTTP_TIMEOUT = 300         # 思考型模型出活慢，读超时给足
HTTP_RETRIES = 3           # 网络错误 / 429 / 5xx 的重试次数

MIN_WORDS = 600            # 简报正文硬性字数下限
MIN_SUBHEADINGS = 3        # 至少 3 个小标题
MIN_DATA_POINTS = 5        # 至少 5 处具体数字（含百分比）
MAX_REPAIR_ROUNDS = 4      # 截断续写 / 扩写的自动修复轮数上限

RETRYABLE_HTTP = {429, 500, 502, 503, 504}

SYSTEM_PROMPT = (
    "你是一名资深汽车行业分析师，为管理层撰写每周市场简报。"
    "你的输出会被原样粘贴进公司周报，因此必须是结构完整、有头有尾、可直接使用的成稿，"
    "绝不允许写到一半中断。"
)

USER_PROMPT = """请撰写一份主题为「2026 年中国新能源汽车出口」的市场简报，要求：

1. 正文（不含标题符号）不少于 900 字，目标 900~1200 字，一次写完整篇；
2. 第一行是一级标题：# 2026 年中国新能源汽车出口市场简报；
3. 使用 Markdown 小标题（## 开头）分节，至少 4 个小节，建议涵盖：
   总量与增速、主要出口目的地与区域结构、头部企业与车型表现、
   挑战与风险（关税/运力/本地化）、下半年趋势展望与建议；
4. 每个小节都必须包含具体数据：出口量、增速、金额、占比、排名、均价等，
   采用口径自洽的合理行业估计，数字要具体（不要只写"大幅增长"）；
5. 以一小段"小结与展望"自然收尾，最后一句必须是完整句子；
6. 只输出简报本身：不要"以下是……"之类引导语，不要客套话，不要解释。"""

CONTINUE_PROMPT = (
    "你上一条回复在输出途中被截断了（达到 max_tokens 限制）。"
    "请从你中断的地方继续写下去：只输出紧接其后的续写内容，不要重复已写内容，"
    "不要重新开头，不要任何解释，一直写到整篇简报按原计划完整收尾（"
    "以「小结与展望」段的完整句子结束）。"
)

EXPAND_APPEND_PROMPT = (
    "当前简报字数不足（约 {words} 字，要求不少于 {min_words} 字）。"
    "请紧接上文继续扩写 1~2 个小节补充深度（可加数据表格式的要点列举），"
    "只输出新增内容，不要重复已有文字，写完后以一段完整的小结自然收尾。"
)

# ---------------------------------------------------------------- 校验工具

_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[.,][A-Za-z0-9]+)*")


def log(msg: str) -> None:
    """进度日志走 stderr，stdout 只留简报正文与最终校验结论。"""
    print(f"[main] {msg}", file=sys.stderr, flush=True)


def count_words(text: str) -> int:
    """保守口径字数：中文字符每字计 1，连续英文/数字串计 1（类似 Word 的"字数"）。

    不计标点与 Markdown 符号，因此该口径不会虚高——它达标则任何常见口径都达标。
    """
    cleaned = re.sub(r"[#*`>|-]", " ", text)
    return len(_CJK_RE.findall(cleaned)) + len(_WORD_RE.findall(cleaned))


def subheadings(text: str) -> list:
    """Markdown 小标题（# ~ ###### 开头的行）。"""
    return re.findall(r"^#{1,6}\s+\S.*$", text, flags=re.MULTILINE)


def data_points(text: str) -> list:
    """文中出现的具体数字（整数/小数，可带 %）。"""
    return re.findall(r"\d+(?:\.\d+)?%?", text)


# 结尾若停在下列字符上，大概率是句中被截断：逗号/顿号/冒号/分号/各类左括号/Markdown 符号。
# 注意句号（。/.）、问号、叹号、右括号都是合法收尾，不能放进黑名单。
_BAD_ENDING_CHARS = "，,、:：;；（(【{［｛#*-\n\t"


def ends_cleanly(text: str) -> bool:
    """启发式判断结尾是否完整（辅助判据，主判据是 finish_reason）。"""
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] not in _BAD_ENDING_CHARS


def diagnose(report: str, finish_reason) -> dict:
    """汇总当前成稿的所有问题，返回 {问题名: 详述}；为空即合格。"""
    words = count_words(report)
    subs = subheadings(report)
    data = data_points(report)
    problems = {}
    if finish_reason not in (None, "stop"):
        problems["finish_reason"] = f"finish_reason={finish_reason}（未自然结束）"
    if words < MIN_WORDS:
        problems["word_count"] = f"字数 {words} < {MIN_WORDS}"
    if len(subs) < MIN_SUBHEADINGS:
        problems["subheadings"] = f"小标题仅 {len(subs)} 个 < {MIN_SUBHEADINGS}"
    if len(data) < MIN_DATA_POINTS:
        problems["data_points"] = f"具体数据仅 {len(data)} 处 < {MIN_DATA_POINTS}"
    if report.strip() and not ends_cleanly(report):
        problems["ending"] = "结尾停在句中标点处，疑似截断"
    if not report.strip():
        problems["empty"] = "正文为空"
    return problems


# ---------------------------------------------------------------- API 调用

def chat_request(api_key: str, messages: list, max_tokens: int) -> dict:
    """调用同步对话补全，带网络层重试；返回 content/finish_reason/model/usage。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning_effort": REASONING_EFFORT,
        "stream": False,
        # 注意：不传 thinking。glm-5.3 在标准端点强制思考，传 disabled 会报 1210。
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            last_err = exc
            log(f"网络异常（第 {attempt}/{HTTP_RETRIES} 次）：{exc}，退避后重试")
            time.sleep(2 ** attempt)
            continue

        if resp.status_code in RETRYABLE_HTTP:
            last_err = f"HTTP {resp.status_code}"
            log(f"HTTP {resp.status_code}（第 {attempt}/{HTTP_RETRIES} 次），退避后重试")
            time.sleep(2 ** attempt)
            continue

        if resp.status_code != 200:
            # 平台业务错误（如 1113 余额不足、1210 参数非法）会带 error.code/message
            try:
                err = resp.json().get("error", {})
                detail = f"{err.get('code', '?')} {err.get('message', resp.text[:300])}"
            except ValueError:
                detail = resp.text[:300]
            raise RuntimeError(f"调用失败 HTTP {resp.status_code}：{detail}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"响应中没有 choices：{str(data)[:300]}")
        choice = choices[0]
        message = choice.get("message") or {}

        # 陷阱 #2/#3：读回实际执行的模型，与请求不一致时报警（同步端点理论不会换）
        echoed = data.get("model") or ""
        if echoed and not echoed.lower().startswith(MODEL):
            log(f"警告：响应回显模型为 {echoed}，与请求的 {MODEL} 不一致，请核对计费与能力")

        return {
            "content": message.get("content") or "",
            "finish_reason": choice.get("finish_reason"),
            "model": echoed,
            "usage": data.get("usage") or {},
        }

    raise RuntimeError(f"重试 {HTTP_RETRIES} 次后仍失败：{last_err}")


# ---------------------------------------------------------------- 生成主流程

def generate_report(api_key: str) -> str:
    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]

    # 第一轮生成。若正文为空且 finish=length，说明预算被思考链吃光（陷阱 #13），
    # 翻倍 max_tokens 重试而不是报错退出。
    max_tokens = INITIAL_MAX_TOKENS
    for attempt in range(3):
        result = chat_request(api_key, base_messages, max_tokens)
        if result["content"].strip() or result["finish_reason"] == "stop":
            break
        log(f"正文为空且 finish_reason={result['finish_reason']}，"
            f"max_tokens {max_tokens} -> {min(max_tokens * 2, MAX_TOKENS_CAP)} 重试")
        max_tokens = min(max_tokens * 2, MAX_TOKENS_CAP)

    report = result["content"]
    finish_reason = result["finish_reason"]
    if result["usage"]:
        log(f"首轮 finish_reason={finish_reason}，"
            f"usage={result['usage'].get('completion_tokens')} completion tokens")

    # 自动修复循环：截断 -> 续写拼接；不达标 -> 追加式扩写。
    for round_no in range(1, MAX_REPAIR_ROUNDS + 1):
        problems = diagnose(report, finish_reason)
        if not problems:
            log(f"第 {round_no - 1} 轮修复后校验通过")
            break
        log(f"修复第 {round_no}/{MAX_REPAIR_ROUNDS} 轮，问题：{problems}")

        # 内容安全拦截重试无意义，直接失败并说明原因
        if finish_reason == "sensitive":
            raise RuntimeError("生成被内容安全策略拦截（finish_reason=sensitive），"
                               "请调整主题措辞后重试")

        truncated = (finish_reason == "length"
                     or "ending" in problems or "empty" in problems)
        messages = list(base_messages)
        messages.append({"role": "assistant", "content": report})
        if truncated:
            messages.append({"role": "user", "content": CONTINUE_PROMPT})
        else:
            messages.append({"role": "user", "content": EXPAND_APPEND_PROMPT.format(
                words=count_words(report), min_words=MIN_WORDS)})

        result = chat_request(api_key, messages, max_tokens)
        addition = result["content"]
        finish_reason = result["finish_reason"]

        if truncated:
            # 从中断处无缝续写：只去掉续写内容开头的换行，其余原样拼接
            report = report + addition.lstrip("\n")
            log(f"续写拼接 {len(addition)} 字符，当前 finish_reason={finish_reason}")
        else:
            if addition.strip():
                # 扩写也按追加处理（绝不整篇替换，避免模型重写时丢内容）
                sep = "" if report.endswith("\n") else "\n\n"
                report = report + sep + addition.strip()
                log(f"追加扩写 {len(addition)} 字符，当前约 {count_words(report)} 字")
            else:
                log("扩写返回为空，下一轮继续尝试")

    return report


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行："
              "export ZHIPUAI_API_KEY=你的Key", file=sys.stderr)
        return 1

    report = generate_report(api_key)

    # ---------------- 最终校验：全过才输出，救不回来就明确失败 ----------------
    words = count_words(report)
    subs = subheadings(report)
    data = data_points(report)
    clean_ending = ends_cleanly(report)

    checks = [
        ("字数", words >= MIN_WORDS,
         f"{words} 字（保守口径：中文字符+英文单词，不含标点与 Markdown 符号），"
         f"要求 ≥ {MIN_WORDS}"),
        ("小标题", len(subs) >= MIN_SUBHEADINGS,
         f"{len(subs)} 个 Markdown 小标题，要求 ≥ {MIN_SUBHEADINGS}"),
        ("具体数据", len(data) >= MIN_DATA_POINTS,
         f"全文出现 {len(data)} 处具体数字，要求 ≥ {MIN_DATA_POINTS}"),
        ("收尾完整", clean_ending, "末尾停在完整句子，无句中截断迹象"),
    ]
    passed = all(ok for _, ok, _ in checks)

    if not passed:
        # 不把残缺内容当成品交付：打印失败原因，退出码非 0
        print("错误：自动修复后简报仍未达标，拒绝输出残缺内容。未通过项：",
              file=sys.stderr)
        for name, ok, detail in checks:
            if not ok:
                print(f"  - {name}: {detail}", file=sys.stderr)
        return 1

    bar = "=" * 64
    print(bar)
    print("市场简报全文（可直接进周报）")
    print(bar)
    print(report.strip())
    print(bar)
    print("校验结论：")
    for name, ok, detail in checks:
        print(f"  [{'通过' if ok else '未过'}] {name}：{detail}")
    print()
    print(f"最终确认：简报完整（收尾正常、无截断），字数 {words} ≥ {MIN_WORDS} 达标，"
          f"含 {len(subs)} 个小标题、{len(data)} 处具体数据，可直接进周报。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
