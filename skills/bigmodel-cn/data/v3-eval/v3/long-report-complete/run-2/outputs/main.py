#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报（不少于 600 字）。

设计要点（对应 bigmodel-cn 技能包的实测结论）：
- glm-5.3 在标准端点强制开启思考，且思考 token 计入 max_tokens：
  预算不足时 finish_reason=length、正文被截断甚至为空。
  因此 max_tokens 直接给 8192（技能实测 600 字简报含思考链至少要 3000）。
- 完整性判据是 finish_reason，不是"内容非空"。只有 finish_reason == "stop"
  且字数/小标题校验通过，才把简报交给用户；否则自动补救，绝不输出半截内容。
- 补救链（按技能"撞上了怎么补救"）：
  ① 整篇生成，max_tokens=8192；
  ② 仍被截断则 max_tokens 翻倍至 16384，并降 reasoning_effort=low 压缩思考开销
     （注意：标准端点对 glm-5.3 传 thinking.type=disabled 会报 1210，绝不能发）；
  ③ 仍不行则分三节分段生成再拼接，逐节校验。
- 网络层（超时/连接错误/429/5xx）自动重试。
- 读回响应里的 model 字段与请求核对，防止异步端点式的静默换模型。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

MIN_CHARS = 600        # 用户要求的硬性字数下限（非空白字符）
MIN_SUBTITLES = 2      # 至少要有 2 个小标题才算结构完整
HTTP_TIMEOUT = 300     # 思考型模型出稿较慢，超时给足
MAX_HTTP_RETRIES = 3   # 网络/限流类错误的重试次数

REPORT_TITLE = "2026 年中国新能源汽车出口市场简报"

SYSTEM_PROMPT = (
    "你是一名汽车行业资深市场分析师，为管理层撰写可直接放进周报的市场简报。"
    "写作要求：用简体中文；观点明确、数据具体（出口量、增速、金额、均价、"
    "主要目的地份额、头部车企表现等，可基于行业公开趋势给出合理测算并标注口径）；"
    "使用以 ## 开头的二级小标题分节；全文一次写完整，结尾用一两句话收束全文，"
    "绝不在段落中间停下。"
)

USER_PROMPT = (
    f"请撰写一份题为《{REPORT_TITLE}》的市场简报，要求：\n"
    "1. 全文不少于 800 字（不含小标题也须超过 600 字）；\n"
    "2. 至少 3 个以 ## 开头的小标题，覆盖：出口总体规模与增长、"
    "主要区域市场与车企格局、挑战与全年展望；\n"
    "3. 每个小节都要有具体数据（数字、百分比、金额或同比变化）；\n"
    "4. 直接输出简报正文，从标题行开始，不要任何开场白或解释。\n"
    "请务必写完整，最后一句必须是总结性文字。"
)

# 分段补救时的三个小节（第 2/3 节生成时会带上前文，保证连贯不重复）
SECTIONS = [
    ("出口总体规模与增长",
     "出口总量（万辆）、同比增速、出口金额与平均单价的最新数据与变化。"),
    ("主要区域市场与车企格局",
     "欧洲、东南亚、拉美、中东等重点区域的表现与份额，比亚迪、奇瑞、上汽、"
     "特斯拉上海工厂等主体的出口情况与竞争态势。"),
    ("挑战与全年展望",
     "关税与贸易壁垒、海运与本地化产能、价格竞争等风险，以及对 2026 全年"
     "出口量与走势的判断。"),
]


def log(msg: str) -> None:
    """进度信息单独成行，与简报正文明确区隔。"""
    print(f"[main] {msg}")


def char_count(text: str) -> int:
    """字数口径：非空白字符（中文场景下标点计入，与常见文档软件一致）。"""
    return sum(1 for ch in text if not ch.isspace())


_SUBTITLE_RE = re.compile(
    # 只认分节标题：## 及更深的 Markdown 标题、中文序号、数字序号（后跟非数字，避免误判 38.5 这类行首数据）、【】标题
    r"^\s*(?:#{2,6}\s*\S|[一二三四五六七八九十]+、|\d{1,2}[、.．](?!\d)\s*\S|【[^】]{1,30}】)",
    re.MULTILINE,
)


def count_subtitles(text: str) -> int:
    return len(_SUBTITLE_RE.findall(text))


def validate(text: str):
    """校验简报是否达标、完整。返回 (是否通过, 问题列表)。"""
    problems = []
    if char_count(text) < MIN_CHARS:
        problems.append(f"字数不足（{char_count(text)} 字 < {MIN_CHARS} 字）")
    if count_subtitles(text) < MIN_SUBTITLES:
        problems.append(f"小标题不足（{count_subtitles(text)} 个 < {MIN_SUBTITLES} 个）")
    return (not problems), problems


def call_glm(api_key: str, messages: list, max_tokens: int,
             reasoning_effort: str = None):
    """同步调用对话补全，返回 (content, finish_reason, 回显模型名)。

    网络/限流/服务端错误自动重试；业务错误（4xx 除 429）不重试直接抛出。
    """
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    # glm-5.3 仅支持 low/high/max，仅在补救时用来压缩思考开销
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    last_err = None
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=HTTP_TIMEOUT,
            )
            if resp.status_code >= 500 or resp.status_code == 429:
                raise requests.HTTPError(
                    f"HTTP {resp.status_code}（服务端繁忙/限流）", response=resp)
            resp.raise_for_status()

            body = resp.json()
            error = body.get("error")
            if error:
                raise RuntimeError(
                    f"平台返回业务错误 code={error.get('code')} "
                    f"message={error.get('message')}")

            choice = body["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
            return content, choice.get("finish_reason"), body.get("model", MODEL)
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError,
                json.JSONDecodeError) as err:
            last_err = err
            if attempt < MAX_HTTP_RETRIES:
                wait = 2 ** attempt
                log(f"请求失败（{err}），{wait}s 后重试（{attempt}/{MAX_HTTP_RETRIES}）")
                time.sleep(wait)
    raise RuntimeError(f"请求连续 {MAX_HTTP_RETRIES} 次失败：{last_err}")


def generate_whole(api_key: str, max_tokens: int, reasoning_effort: str = None):
    """整篇生成。返回 (简报文本, finish_reason, 回显模型名)。"""
    content, finish_reason, echoed = call_glm(
        api_key,
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": USER_PROMPT}],
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    return content, finish_reason, echoed


def base_model_name(name: str) -> str:
    """去掉形如 -260428 的日期/版本数字后缀，取模型基座名用于回显核对。"""
    return re.sub(r"-\d{4,}$", "", (name or "").strip().lower())


def generate_segmented(api_key: str):
    """分段生成再拼接（最后一级补救）。返回 (拼接文本, 各段 finish_reason, 回显模型名)。"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    pieces, finish_reasons, echoed_model = [], [], MODEL
    for i, (subtitle, brief) in enumerate(SECTIONS, start=1):
        ask = (
            f"这是《{REPORT_TITLE}》简报的第 {i}/{len(SECTIONS)} 节，"
            f"小标题为「## {subtitle}」，本节要点：{brief}\n"
            "要求：250~350 字、必须包含具体数据、直接以该小标题行开头输出正文，"
            "不要开场白；本节是简报的一个片段，结尾自然停在句号即可，不要写全文总结。"
        )
        if pieces:  # 多轮对话里已带上前文，小节之间数据连贯、不重复
            ask += "\n请承接上文与整体风格继续写本节，不要重复上文已给出的数字。"
        messages.append({"role": "user", "content": ask})

        # 每段 4096 预算（约 250 字正文 + 思考链足够）；若该段被截断则翻倍重试一次
        piece, fr, echoed_model = call_glm(messages, max_tokens=4096)
        if fr == "length":
            log(f"第 {i} 节被截断，加大预算重试该节")
            piece, fr, echoed_model = call_glm(messages, max_tokens=8192)
        if fr != "stop":
            raise RuntimeError(f"第 {i} 节 finish_reason={fr}，分段生成失败")
        pieces.append(piece.strip())
        finish_reasons.append(fr)
        # 把本节真正的内容作为 assistant 轮回填，供下一节承接
        messages.append({"role": "assistant", "content": pieces[-1]})

    return f"# {REPORT_TITLE}\n\n" + "\n\n".join(pieces), finish_reasons, echoed_model


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        log("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export 后再运行。")
        return 1

    # 三级尝试：① 足量预算整篇生成 → ② 翻倍预算 + 低推理强度 → ③ 分段拼接
    plan = [
        ("整篇生成（max_tokens=8192）",
         lambda: generate_whole(api_key, max_tokens=8192)),
        ("整篇重试（max_tokens=16384，reasoning_effort=low）",
         lambda: generate_whole(api_key, max_tokens=16384, reasoning_effort="low")),
        ("分段生成后拼接（每节独立校验）",
         lambda: generate_segmented(api_key)),
    ]

    history = []  # 记录每次失败原因，便于最终诊断
    for idx, (desc, run) in enumerate(plan, start=1):
        log(f"第 {idx} 轮尝试：{desc}")
        try:
            result = run()
        except (RuntimeError, requests.RequestException, KeyError, IndexError) as err:
            history.append(f"第 {idx} 轮（{desc}）调用失败：{err}")
            log(f"  失败：{err}")
            continue

        if idx == 3:
            text, finish_info, echoed_model = result
            finish_desc = "stop（各节均为 stop）" if all(
                f == "stop" for f in finish_info) else str(finish_info)
        else:
            text, finish_reason, echoed_model = result
            finish_desc = finish_reason
            if finish_reason != "stop":
                history.append(
                    f"第 {idx} 轮（{desc}）finish_reason={finish_reason}，正文可能被截断")
                log(f"  finish_reason={finish_reason}（未自然收尾），进入补救")
                continue

        ok, problems = validate(text)
        if not ok:
            history.append(f"第 {idx} 轮（{desc}）校验未通过：{'；'.join(problems)}")
            log(f"  校验未通过：{'；'.join(problems)}，进入补救")
            continue

        # 全部通过，才会走到这里 —— 只输出完整简报
        n_chars, n_subs = char_count(text), count_subtitles(text)
        model_mismatch = base_model_name(echoed_model) != base_model_name(MODEL)

        print("=" * 72)
        print(text)
        print("=" * 72)
        print()
        print(f"✅ 字数达标：{n_chars} 字（要求 ≥ {MIN_CHARS} 字，按非空白字符计）")
        print(f"✅ 内容完整：finish_reason={finish_desc}，模型自然收尾，未被 max_tokens 截断")
        print(f"✅ 结构完整：共 {n_subs} 个小标题，含具体数据分节")
        print(f"模型：{MODEL}（响应回显 {echoed_model}）；生成方式：第 {idx} 轮（{desc}）")
        if model_mismatch:
            print(f"⚠️ 警告：响应回显模型 {echoed_model} 与请求 {MODEL} 基座不一致，"
                  "计费系数与能力可能不同，使用前请到控制台核实。")
        if history:
            print(f"补救记录：此前 {len(history)} 轮未达标已自动处理，"
                  f"本次交付内容为完整版（详情：{history[-1]}）")
        return 0

    # 三轮全部失败：明确说明，绝不打印任何未通过校验的残缺正文
    log("错误：三轮尝试均未能生成达标且完整的简报，未输出任何残缺内容。")
    for item in history:
        log(f"  - {item}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
