#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《2026 年中国新能源汽车出口》市场简报生成器（智谱 GLM，open.bigmodel.cn）

硬约束：下游网关限制「单次请求 max_tokens 绝对不能超过 1000」，不可协商。
应对策略：
  1. 分段生成：全文拆成 4 个小节，每节一次独立请求，单次只申请
     SECTION_MAX_TOKENS = 800，任何一次请求都远低于 1000 硬顶；
  2. 发送前再钳位一次（HARD_MAX_TOKENS_PER_REQUEST = 1000），双保险；
  3. glm-5.3 在标准端点无法关闭思考（thinking.type="disabled" 会报 1210），而思考
     token 会计入 max_tokens。因此统一传 reasoning_effort="low"（官方与实测均表明
     low 档实际不产生思考 token），避免思考挤占输出预算、导致 finish_reason=length
     把正文截断；
  4. 每段校验 finish_reason == "stop" 且非空；拼接后在客户端统计汉字数，
     不足 600 自动补写（补写同样受预算约束）；仍不达标则报清卡点、退出非零，
     不交付半成品。

运行方式：
    ZHIPUAI_API_KEY=你的Key python3 main.py
依赖：仅 requests + Python 标准库。
"""

import os
import re
import sys
import time
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

# ---- 网关预算硬约束（不可协商） ----
HARD_MAX_TOKENS_PER_REQUEST = 1000  # 单次请求 max_tokens 的绝对上限
SECTION_MAX_TOKENS = 800            # 每段实际申请值，预留约 20% 安全余量

# ---- 简报交付要求 ----
TARGET_BODY_HANZI = 600             # 正文（不含大小标题）汉字数下限

HTTP_RETRIES = 3                    # 单次 HTTP 调用的网络层重试次数
SECTION_ATTEMPTS = 3                # 每个小节的内容层重试次数
TOPUP_MAX_ROUNDS = 3                # 字数不足时的补写轮数上限

REQUEST_TIMEOUT = 120

# 每次请求的 completion_tokens 记录，用于最后核验预算约束
TOKEN_LOG = []

# 提供给模型的参考数据（输入 token 不受 max_tokens 限制，故放这里以锚定数字）。
# 口径：2023-2024 为中汽协等公开报道数字；2025-2026 为脚本内置的情景估算，
# 接真实数据源时可整体替换本常量。
FACT_SHEET = """【参考数据（写作只允许使用这里的数字）】
- 2023 年中国新能源汽车出口 120.3 万辆；
- 2024 年中国新能源汽车出口 128.4 万辆，约占当年整车出口总量 585.9 万辆的 21.9%；
- 2024 年新能源汽车主要流向：比利时、巴西、泰国、英国、澳大利亚、以色列等；
- 2024 年比亚迪海外销量约 40 万辆量级，名爵、奇瑞、长城等亦为主要出海主体；
- 欧盟自 2024 年 10 月起对中国产纯电动车加征反补贴关税（在 10% 基础税率之上，各家税率不同）；
- 2025 年中国新能源汽车出口约 155 万辆（全年口径，内部估算）；
- 2026 年上半年出口约 95 万辆（情景估算），2026 年全年预计 180 万至 210 万辆（情景区间）；
- 2026 年行业关键词：欧盟关税应对、匈牙利/泰国/巴西本地化建厂、插混与增程出海提速、滚装运力与汇率波动。"""

SYSTEM_PROMPT = """你是一名汽车行业市场分析师，为《2026 年中国新能源汽车出口市场简报》撰写正文的指定小节。
写作规则（必须严格遵守）：
1. 只输出该小节的正文段落本身：不写小标题、不写序号、不加引号、不用任何 markdown 记号、不写"好的/以下是"之类引语，也不做任何解释；
2. 正文为一段连续文字，长度必须落在用户给定的汉字数区间内（口径：汉字，不含标点与数字）；
3. 所有数字只能来自用户提供的【参考数据】；参考数据未覆盖的内容用定性描述或区间表述，禁止编造新的精确数字；
4. 简体中文书面语，信息密度高，避免空话。"""

SECTIONS = [
    {
        "heading": "一、总体规模与增长",
        "brief": "概述 2026 年上半年中国新能源汽车出口总量（用情景估算值）与同比变化、"
                 "在整车出口中的地位，并用一句话衔接 2023-2025 年的走势。",
        "lo": 170,
        "hi": 230,
    },
    {
        "heading": "二、区域市场格局",
        "brief": "描绘主要出口目的地结构：欧洲（比利时、英国）、拉美（巴西、墨西哥）、"
                 "东南亚（泰国）、中东（阿联酋、以色列）的相对地位与变化，"
                 "并点出欧盟关税落地后的路径变化（经枢纽港中转、转向插混等）。",
        "lo": 170,
        "hi": 230,
    },
    {
        "heading": "三、竞争态势与产业链",
        "brief": "概述头部出海主体（比亚迪、名爵、奇瑞、长城等）海外表现的量级、"
                 "价格带竞争，以及匈牙利/泰国/巴西本地化建厂与供应链跟随出海的进展。",
        "lo": 170,
        "hi": 230,
    },
    {
        "heading": "四、风险与趋势展望",
        "brief": "总结 2026 年的主要风险（欧盟反补贴关税、贸易壁垒多元化、滚装运力与汇率波动）"
                 "与全年出口区间预测，最后以一句数据口径说明收尾（注明 2026 年数字为情景估算）。",
        "lo": 170,
        "hi": 230,
    },
]

TOPUP_HEADING = "五、延伸观察"


def log(msg):
    print(msg, file=sys.stderr)


def hanzi_count(text):
    """统计汉字数（不含标点、数字、字母与空白）。"""
    return len(re.findall(r"[一-鿿]", text))


def chat(messages, max_tokens, api_key):
    """调用同步 chat/completions，返回 (content, finish_reason, usage)。

    任何一次请求的 max_tokens 都会被钳位在 HARD_MAX_TOKENS_PER_REQUEST 以内；
    传入超限值直接抛错，保证硬约束在代码路径上不可违反。
    """
    if max_tokens > HARD_MAX_TOKENS_PER_REQUEST:
        raise ValueError(
            f"违反硬约束：单次请求 max_tokens={max_tokens} "
            f"超过网关上限 {HARD_MAX_TOKENS_PER_REQUEST}"
        )
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": min(int(max_tokens), HARD_MAX_TOKENS_PER_REQUEST),
        "temperature": 0.3,
        "stream": False,
        # glm-5.3 在标准端点无法关闭思考（disabled 会报 1210），
        # low 档实测 reasoning_tokens=0，等效不思考，保住输出预算
        "reasoning_effort": "low",
        "request_id": uuid.uuid4().hex,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络异常: {exc}"
            log(f"[{attempt}/{HTTP_RETRIES}] {last_err}，{2 * attempt} 秒后重试")
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"HTTP {resp.status_code}"
            log(f"[{attempt}/{HTTP_RETRIES}] {last_err}，{2 * attempt} 秒后重试")
            time.sleep(2 * attempt)
            continue

        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(f"响应不是 JSON: {resp.text[:200]!r}")

        resp.raise_for_status()
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            raise RuntimeError(
                f"API 业务错误 {err.get('code')}: {err.get('message')}"
            )

        choice = body["choices"][0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        finish = choice.get("finish_reason")
        usage = body.get("usage") or {}

        # 异步端点会静默换模型，同步端点按理不会；读回核对，不一致即报警
        echoed = body.get("model")
        if echoed and echoed != MODEL:
            log(f"警告：响应 model={echoed} 与请求 {MODEL} 不一致，请核对计费与行为")

        TOKEN_LOG.append(usage.get("completion_tokens"))
        return content, finish, usage

    raise RuntimeError(f"请求连续 {HTTP_RETRIES} 次失败，最后错误：{last_err}")


def clean_paragraph(text):
    """去掉模型可能违规带出的 markdown 标题行、空行与包裹引号。"""
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    text = "".join(lines).strip()
    return text.strip("\"'“”‘’").strip()


def generate_section(heading, brief, lo, hi, api_key):
    """生成一个小节正文，带内容层重试（截断/过短/异常结束都会重试）。"""
    user_msg = (
        f"{FACT_SHEET}\n\n【本次任务】\n{brief}\n\n"
        f"【长度硬要求】本段正文 {lo}~{hi} 个汉字（不含标点与数字）。"
        f"只输出这一段正文本身。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    last_err = None
    for attempt in range(1, SECTION_ATTEMPTS + 1):
        content, finish, usage = chat(messages, SECTION_MAX_TOKENS, api_key)
        text = clean_paragraph(content)
        reasoning = ((usage.get("completion_tokens_details") or {})
                     .get("reasoning_tokens"))
        if reasoning:
            log(f"提示：小节[{heading}] reasoning_tokens={reasoning}，思考在消耗输出预算")
        if finish == "length":
            last_err = (f"第 {attempt} 次尝试 finish_reason=length"
                        f"（max_tokens={SECTION_MAX_TOKENS} 被打满，内容疑被截断）")
            log(f"小节[{heading}] {last_err}，重试")
            continue
        if finish != "stop":
            last_err = f"第 {attempt} 次尝试 finish_reason={finish}（异常结束）"
            log(f"小节[{heading}] {last_err}，重试")
            continue
        n = hanzi_count(text)
        if n < lo - 50:
            last_err = f"第 {attempt} 次尝试正文仅 {n} 汉字，低于容忍线 {lo - 50}"
            log(f"小节[{heading}] {last_err}，重试")
            continue
        return text
    raise RuntimeError(
        f"小节[{heading}]连续 {SECTION_ATTEMPTS} 次未产出合格内容，最后问题：{last_err}"
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        log("卡点：环境变量 ZHIPUAI_API_KEY 未设置（当前环境无 Key，属预期）。"
            "请到 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取后以 "
            "ZHIPUAI_API_KEY=xxx python3 main.py 方式运行。")
        sys.exit(2)

    parts = []  # [(小标题, 正文段落)]
    try:
        for sec in SECTIONS:
            log(f"生成小节：{sec['heading']} ...")
            parts.append((sec["heading"],
                          generate_section(sec["heading"], sec["brief"],
                                           sec["lo"], sec["hi"], api_key)))

        # ---- 客户端字数校验，不足则补写 ----
        topup_paras = []
        rounds = 0
        while (sum(hanzi_count(p) for _, p in parts)
               + sum(hanzi_count(p) for p in topup_paras)) < TARGET_BODY_HANZI \
                and rounds < TOPUP_MAX_ROUNDS:
            rounds += 1
            covered = "、".join(h for h, _ in parts)
            log(f"正文汉字数不足 {TARGET_BODY_HANZI}，补写第 {rounds} 轮 ...")
            brief = (f"简报前文已覆盖：{covered}。"
                     f"请从充电与售后网络建设、滚装船运力与海运价、汇率与结算、"
                     f"出口信用保险等运营侧角度中，选取前文尚未展开的 2~3 个角度补充一段。")
            topup_paras.append(
                generate_section(TOPUP_HEADING, brief, 150, 210, api_key))
    except RuntimeError as exc:
        log(f"\n生成失败，卡点：{exc}")
        if parts:
            log("【半成品，仅供排查，非交付物】")
            for h, p in parts:
                log(f"## {h}\n{p}\n")
        sys.exit(1)

    body_hanzi = (sum(hanzi_count(p) for _, p in parts)
                  + sum(hanzi_count(p) for p in topup_paras))
    if body_hanzi < TARGET_BODY_HANZI:
        detail = "、".join(f"{h}:{hanzi_count(p)}字" for h, p in parts)
        log(f"卡点：补写 {TOPUP_MAX_ROUNDS} 轮后正文仍只有 {body_hanzi} 汉字"
            f"（要求 ≥{TARGET_BODY_HANZI}）。各小节：{detail}。"
            f"半成品已拒绝交付。")
        sys.exit(1)

    # ---- 拼装全文 ----
    title = "2026 年中国新能源汽车出口市场简报"
    lines = [title, ""]
    for heading, para in parts:
        lines += [f"## {heading}", "", para, ""]
    if topup_paras:
        lines += [f"## {TOPUP_HEADING}", ""]
        lines += [para + "\n" for para in topup_paras]
    full = "\n".join(lines).strip()

    # ---- 打印全文与实际字数 ----
    print("=" * 22 + " 简报全文 " + "=" * 22)
    print(full)
    print()
    print("=" * 22 + " 字数统计 " + "=" * 22)
    print(f"正文汉字数（不含大小标题，要求 ≥{TARGET_BODY_HANZI}）: {body_hanzi}")
    print(f"全文汉字数（含标题）: {hanzi_count(full)}")
    print(f"全文总字符数（含标点、数字、空白）: {len(full)}")
    print(f"请求预算: 共 {len(TOKEN_LOG)} 次请求，单次 max_tokens={SECTION_MAX_TOKENS}"
          f"（网关硬顶 {HARD_MAX_TOKENS_PER_REQUEST}，全部未超）")
    print(f"各请求 completion_tokens: {TOKEN_LOG}")


if __name__ == "__main__":
    main()
