#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成《2026年中国新能源汽车出口市场简报》（正文不少于 600 汉字，含小标题与数据）。

硬约束：下游网关限制，任何一次请求的 max_tokens 绝对不能超过 1000。

为什么不能"一次请求直接生成全文"：
  1) 平台的思考(reasoning)token 计入 max_tokens——预算给小了会 finish_reason=length、
     正文为空或被截断；
  2) glm-5.3 / glm-5.3-flash 在标准端点强制开启思考（传 thinking.disabled 报 1210），
     1000 的预算会被思考链吃掉大半；
  3) glm-4.6 支持显式传 thinking.type=disabled，可以把预算全部留给正文。
因此本脚本的策略：
  - 模型选 glm-4.6 并关闭 thinking（若端点参数校验拒绝，自动降级为不传该参数重试，
    max_tokens 上限保持不变）；
  - 分段生成 + 本地拼接：每个小节单独一次请求（目标约 200 汉字），
    每次请求 max_tokens 固定为 MAX_TOKENS_PER_REQUEST(=1000，含安全余量)，
    总字数由客户端拼接收口到 ≥600 汉字；
  - 逐请求检查 finish_reason：length 截断时缩小该节目标字数重试（绝不放大 max_tokens）；
  - 拼接后不足 600 汉字则自动追加补充小节；仍不足才判失败，并打印完整卡点诊断，
    不输出半截结果。

API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖 requests 与标准库。
用法：python3 main.py
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"

# ---- 网关硬约束：任何一次请求的 max_tokens 都不得超过该值，代码里唯一取值点 ----
MAX_TOKENS_PER_REQUEST = 1000

TARGET_BODY_HAN = 600   # 正文（不含大标题与小标题）必须达到的最低汉字数
REQUEST_TIMEOUT = 120   # 单次 HTTP 超时（秒）
TRANSIENT_RETRIES = 3   # 网络/限流/5xx 的重试次数
SECTION_RETRIES = 3     # 单个小节生成（截断/敏感/空内容）的重试次数

SYS_PROMPT = (
    "你是一名汽车行业市场分析师，为《2026年中国新能源汽车出口市场简报》撰写小节。"
    "要求：中文书面语，一段成文；必须引用具体数据（出口量、增速、金额、份额等，"
    "可基于近年公开趋势给出合理估计并写明量级）；只输出正文段落本身，"
    "不要输出小标题、列表、分点、开场白或收尾客套。"
)

# 基础小节：(小标题, 写作指令, 目标汉字数)。四节合计目标约 780 字，留出富余。
SECTIONS = [
    ("一、出口总量与增长态势",
     "概述2026年中国新能源汽车出口的总体规模与增长：全年出口量（万辆）、同比增速、"
     "纯电动与插电混动的结构占比、出口金额与平均单车价格的变化。",
     200),
    ("二、重点区域市场格局",
     "分析2026年出口目的地分布：欧洲、东南亚、中东、拉美、中亚等区域的占比与变化，"
     "至少给出两个代表国家的销量或增速数据，并点出此消彼长的结构性变化。",
     200),
    ("三、竞争格局与头部车企",
     "分析2026年出口竞争格局：比亚迪、奇瑞、上汽、吉利等头部车企的出口量与份额，"
     "新势力与传统车企的不同打法，价格竞争与品牌溢价的走向。",
     190),
    ("四、风险挑战与全年展望",
     "分析2026年出口的主要风险（欧盟反补贴税等贸易壁垒、本地化合规、海运运力、汇率），"
     "并对全年出口量级与结构给出明确的展望判断。",
     190),
]

# 拼接后不足 600 汉字时，按序追加的补量小节
TOPIC_BACKUPS = [
    ("五、产业链出海与本地化生产",
     "分析2026年动力电池与零部件随整车出海、海外建厂（泰国、匈牙利、巴西等）的进展，"
     "说明本地化产能对出口结构的替代与放大效应，引用至少两个具体数据。"),
    ("六、海运运力与滚装船瓶颈",
     "分析2026年汽车滚装船运力与运价变化对出口的影响，引用运力增速、运价涨跌幅等"
     "具体数据，并说明车企自建船队的应对。"),
]

# 常见错误码的人话提示（用于失败诊断）
ERROR_HINTS = {
    "1113": "疑似 GLM Coding Plan 套餐 Key 打了标准端点（两套计费体系不通用），"
            "请改用标准 API Key，或将端点换为 …/api/coding/paas/v4。",
    "1210": "参数或模型名不被当前端点接受，请核对模型与参数。",
}


class ApiError(Exception):
    """调用 chat/completions 失败（网络、限流、平台报错等）。"""


def han_count(text):
    """统计汉字数（仅 CJK 基本区），标点、数字、字母不计入。"""
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def parse_api_error(resp):
    """从错误响应里提取 {"error":{"code":..,"message":..}}，提取失败则给原始片段。"""
    try:
        err = (resp.json() or {}).get("error") or {}
        if err:
            return "code={0} message={1}".format(err.get("code"), err.get("message"))
    except ValueError:
        pass
    return resp.text[:300]


def chat(api_key, messages, max_tokens, state):
    """发起一次对话请求，返回 (content, finish_reason)。

    网关硬约束在此收口：max_tokens 一旦超过 MAX_TOKENS_PER_REQUEST 直接拒绝，
    不发请求。
    """
    if max_tokens > MAX_TOKENS_PER_REQUEST:
        raise ApiError(
            "拒绝发请求：max_tokens={0} 超过网关硬约束 {1}".format(
                max_tokens, MAX_TOKENS_PER_REQUEST)
        )

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,       # 每次请求都是同一个 ≤1000 的值
        "temperature": 0.6,
    }
    if state["use_thinking_disabled"]:
        # 关闭思考，避免推理 token 挤占 max_tokens 预算（glm-4.6 支持显式关闭）
        payload["thinking"] = {"type": "disabled"}

    headers = {
        "Authorization": "Bearer {0}".format(api_key),
        "Content-Type": "application/json",
    }

    last_err = "未知错误"
    for attempt in range(1, TRANSIENT_RETRIES + 1):
        state["requests"] += 1
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = "网络异常: {0}".format(exc)
            time.sleep(2 * attempt)
            continue

        # 限流与 5xx 视为瞬时故障，退避重试
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = "HTTP {0}: {1}".format(resp.status_code, resp.text[:200])
            time.sleep(2 * attempt)
            continue

        if resp.status_code != 200:
            raise ApiError("HTTP {0} {1}".format(resp.status_code, parse_api_error(resp)))

        try:
            body = resp.json()
        except ValueError:
            raise ApiError("HTTP 200 但响应不是 JSON: {0}".format(resp.text[:300]))

        # 防御：个别能力域会在 HTTP 200 里带 error 体，chat 正常不会，但顺手兜住
        if body.get("error"):
            err = body["error"]
            raise ApiError("HTTP 200 但返回 error code={0} message={1}".format(
                err.get("code"), err.get("message")))

        choices = body.get("choices") or []
        if not choices:
            raise ApiError("响应缺少 choices: {0}".format(str(body)[:300]))

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        return content, choices[0].get("finish_reason")

    raise ApiError("重试 {0} 次后仍失败，最后错误：{1}".format(TRANSIENT_RETRIES, last_err))


def clean_content(raw, title):
    """轻度清洗：去 markdown 围栏、去模型复述的小标题，压成单段。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        nl = text.find("\n")
        text = text[nl + 1:] if nl != -1 else ""
        text = text.rstrip()
        if text.endswith("```"):
            text = text[:-3]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        head = lines[0].strip("《》#* ：:")
        if head == title or title in head or head in title:
            lines = lines[1:]
    return "".join(lines)


def generate_section(api_key, state, title, instruction, target_chars, context):
    """生成一个小节，返回 (段落正文, 过程诊断列表)。拿不到完整段落则抛 ApiError。"""
    target = target_chars
    notes = []
    for attempt in range(1, SECTION_RETRIES + 1):
        user = (
            "简报主题：2026年中国新能源汽车出口。\n"
            + ("已定稿的上文（保持衔接，不要重复其中内容）：\n" + context + "\n"
               if context else "")
            + "本节任务：" + instruction + "\n"
            + "篇幅要求：{0} 个汉字左右，一段成文。".format(target)
        )
        messages = [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user},
        ]
        try:
            content, finish = chat(api_key, messages, MAX_TOKENS_PER_REQUEST, state)
        except ApiError as exc:
            msg = str(exc)
            # 端点拒绝 thinking 参数（1210）时降级为不传该参数重试一次；
            # max_tokens 约束不变
            if state["use_thinking_disabled"] and "1210" in msg:
                state["use_thinking_disabled"] = False
                notes.append("[{0}] 端点拒绝 thinking 参数，已降级为不传该参数（"
                             "max_tokens 仍为 {1}）".format(title, MAX_TOKENS_PER_REQUEST))
                continue
            raise

        content = clean_content(content, title)
        count = han_count(content)
        if finish == "stop" and count >= 80:
            if count < target - 60:
                notes.append("[{0}] 实得 {1} 字略低于目标 {2} 字，但完整可用".format(
                    title, count, target))
            return content, notes

        if finish == "length":
            # 截断：缩小该节目标字数重试，绝不放大 max_tokens
            notes.append("[{0}] 第 {1} 次输出在 max_tokens={2} 内被截断"
                         "(finish_reason=length，实得 {3} 字)，缩小目标字数重试".format(
                             title, attempt, MAX_TOKENS_PER_REQUEST, count))
            target = max(100, target // 2)
        else:
            # sensitive / network_error / 空内容等
            notes.append("[{0}] 第 {1} 次异常 finish_reason={2}，实得 {3} 字，重试".format(
                title, attempt, finish, count))
        time.sleep(2)

    raise ApiError("[{0}] 连续 {1} 次未取得完整段落。过程诊断：{2}".format(
        title, SECTION_RETRIES, "；".join(notes) or "无"))


def assemble(collected):
    """拼装最终简报文本，返回 (全文, 正文汉字数, 含标题总汉字数)。"""
    lines = ["2026年中国新能源汽车出口市场简报", ""]
    for title, para in collected:
        lines.extend([title, para, ""])
    doc = "\n".join(lines).rstrip() + "\n"
    body_han = sum(han_count(para) for _, para in collected)
    return doc, body_han, han_count(doc)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("卡点：环境变量 ZHIPUAI_API_KEY 未设置（或为空）。"
              "请先 export ZHIPUAI_API_KEY=<你的标准 API Key> 再运行。"
              "未发起任何请求，本次没有产出。", file=sys.stderr)
        return 1

    state = {"use_thinking_disabled": True, "requests": 0}
    collected = []          # [(小标题, 段落)]
    notes = []              # 过程诊断
    failures = []           # 失败小节
    context = ""

    queue = [(t, ins, tgt) for t, ins, tgt in SECTIONS]
    backup_iter = iter(TOPIC_BACKUPS)

    while True:
        body_han = sum(han_count(p) for _, p in collected)
        if body_han >= TARGET_BODY_HAN:
            break
        if queue:
            title, instruction, target = queue.pop(0)
        else:
            nxt = next(backup_iter, None)
            if nxt is None:
                break
            title, instruction = nxt
            target = 200
            notes.append("正文不足 {0} 字，自动追加补量小节：{1}".format(
                TARGET_BODY_HAN, title))
        try:
            para, sec_notes = generate_section(api_key, state, title, instruction,
                                               target, context)
            notes.extend(sec_notes)
            collected.append((title, para))
            context = (context + "\n" + para).strip()
        except ApiError as exc:
            failures.append(str(exc))

    doc, body_han, total_han = assemble(collected)

    # ---- 结果判定：拿不到合格全文就说清卡点，不输出半截结果 ----
    if body_han < TARGET_BODY_HAN:
        print("本次未能产出合格简报（正文 {0} 字 < 要求 {1} 字），不输出半截结果。"
              .format(body_han, TARGET_BODY_HAN), file=sys.stderr)
        print("卡点诊断：", file=sys.stderr)
        if failures:
            for f in failures:
                print("  - 失败小节：{0}".format(f), file=sys.stderr)
        else:
            print("  - 各小节请求均完成，但模型输出总字数不足（可重跑或调大 SECTIONS 目标字数）。",
                  file=sys.stderr)
        for code, hint in ERROR_HINTS.items():
            joined = " ".join(failures)
            if code in joined:
                print("  - 错误码 {0} 提示：{1}".format(code, hint), file=sys.stderr)
        print("  - 共发起 {0} 次请求，单次 max_tokens 均为 {1}（未超过网关硬约束）。".format(
            state["requests"], MAX_TOKENS_PER_REQUEST), file=sys.stderr)
        for n in notes:
            print("  - 过程：{0}".format(n), file=sys.stderr)
        return 1

    # ---- 成功：打印全文与实际字数 ----
    print(doc)
    print("=" * 56)
    print("【字数统计】正文汉字数：{0} 字（要求 ≥ {1} 字，已达标）".format(
        body_han, TARGET_BODY_HAN))
    print("【字数统计】含大标题与小标题合计：{0} 汉字".format(total_han))
    print("【请求合规】共 {0} 次请求，单次 max_tokens={1}，均未超过 1000（网关硬约束）".format(
        state["requests"], MAX_TOKENS_PER_REQUEST))
    for n in notes:
        print("【生成说明】{0}".format(n), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
