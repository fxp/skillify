#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报。

要求：不少于 600 字、有小标题、有具体数据、内容完整（不能截断半截），
生成后打印全文并明确确认字数达标、内容完整。

实现要点（对应 bigmodel-cn 技能包的实测陷阱）：
- 截断判据用 finish_reason 而不是"内容非空"：glm-5.3 的思考 token 也计入
  max_tokens，预算不足时 finish_reason=length、正文被拦腰截断（陷阱 #13）。
  因此给足 max_tokens，并在收到 length 时把半截正文回传给模型、从中断处
  续写拼接，直到 finish_reason=stop 自然收尾。
- 标准端点不传 thinking.type=disabled：glm-5.3 在标准端点强制开思考，
  传 disabled 会报 1210 参数错误（陷阱 #14）。
- 429/5xx/网络错误做指数退避重试；1113（余额/套餐 Key 打错端点）和
  400/401/403 属配置问题，不重试、直接报清楚原因。
- 生成后硬校验：字数（不含空白）>=600、小标题 >=3 个、含数字数据、
  末句收束完整；不达标就带问题让模型重写整篇，仍不达标则报错退出，
  绝不把半截内容当成品输出。

运行：ZHIPUAI_API_KEY=你的Key python3 main.py
依赖：仅 requests。
"""

import os
import re
import sys
import time
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"          # 标准端点旗舰对话模型，最大输出 128K
MAX_TOKENS = 8192          # 思考 token 也计入 max_tokens，给足余量防截断
REQUEST_TIMEOUT = (10, 300)  # (连接超时, 读超时)：思考模型出长文较慢，读超时放宽
HTTP_RETRIES = 3           # 429/5xx/网络错误 的退避重试次数
MAX_CONTINUE_ROUNDS = 6    # 单篇内 finish_reason=length 的最大续写轮数
MAX_DRAFT_ATTEMPTS = 3     # 整篇生成（含校验失败重写）的最大尝试次数
MIN_BODY_CHARS = 600       # 正文字数下限（按不含空白字符统计，口径更严）
MIN_SECTIONS = 3           # 小标题数量下限

SYSTEM_PROMPT = (
    "你是一名资深新能源汽车行业分析师，为管理层周报撰写市场简报。"
    "文风专业克制，观点必须有数据支撑；对 2026 年的展望可基于 2024-2025 年"
    "公开趋势给出合理估计，并标注为估计值。"
)

USER_PROMPT = """请撰写一份主题为「2026 年中国新能源汽车出口」的市场简报，要求：

1. 全文不少于 900 字（中文正文，请留足余量）；
2. 用 Markdown 二级小标题（## ）划分至少 4 个部分，例如：总量与增速、区域市场结构、头部企业表现、风险与展望；
3. 每个部分都必须包含具体数据（出口量、同比增速、市场份额、平均单价、目的地国家占比等）；
4. 结尾用一段「小结与展望」自然收束全文，写完整的段落；
5. 直接输出简报正文（从总标题开始），不要任何开场白、寒暄或解释。"""

CONTINUE_PROMPT = (
    "上一段输出因长度限制被截断了。请从中断处继续往下写，不要重复已写内容，"
    "不要任何过渡语或解释，直到整篇简报写完并自然收尾。"
)

REPAIR_PROMPT_TEMPLATE = """你之前写的简报稿件未通过质量校验，问题如下：
{issues}

请重写一份完整的简报，要求：
1. 修复上述全部问题；
2. 主题仍为「2026 年中国新能源汽车出口」，全文不少于 900 字，至少 4 个 Markdown
   二级小标题（## ），每部分含具体数据，结尾有完整的「小结与展望」段落；
3. 直接输出修订后的完整全文（从总标题开始），不要任何解释。

未通过的稿件（供参考，不要原样照搬）：
{draft}"""


class GenerationError(RuntimeError):
    """生成流程中不可恢复的错误。"""


# ---------------------------------------------------------------- 校验工具

# 末字符是这些句读/收束符号之一，视为"写完了"而不是半截
_TERMINAL_CHARS = set("。！？；：”』」）)】》>.!?:;\"'")


def count_chars(text):
    """正文字数：不含空白字符（比含空白的口径更严格）。"""
    return sum(1 for ch in text if not ch.isspace())


def count_sections(text):
    """Markdown 小标题数量（# 到 ###### 开头的行）。"""
    return len(re.findall(r"(?m)^\s{0,3}#{1,6}\s+\S", text))


def has_data(text):
    return bool(re.search(r"\d", text))


def ends_like_finished(text):
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in _TERMINAL_CHARS


def validate(report):
    """返回问题列表；空列表 = 合格。"""
    issues = []
    n = count_chars(report)
    if n < MIN_BODY_CHARS:
        issues.append(f"字数不足：正文 {n} 字（不含空白），要求 ≥{MIN_BODY_CHARS} 字")
    s = count_sections(report)
    if s < MIN_SECTIONS:
        issues.append(f"小标题不足：仅 {s} 个，要求 ≥{MIN_SECTIONS} 个")
    if not has_data(report):
        issues.append("缺少具体数据（全文没有任何数字）")
    if not ends_like_finished(report):
        issues.append("结尾不完整（末字符不是句读符号），疑似截断")
    return issues


# ---------------------------------------------------------------- HTTP 层

def _backoff_sleep(attempt):
    time.sleep(min(2 ** attempt, 15))


def chat_completion(api_key, messages):
    """调一次同步 chat/completions，返回解析后的 JSON dict。

    仅 429（不含 1113）/5xx/网络错误重试；其余直接抛 GenerationError。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "stream": False,  # 非流式：finish_reason 一次性拿到，判截断最可靠
        "request_id": uuid.uuid4().hex,  # 6-64 字符，便于平台侧排查
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络错误：{exc!r}"
            if attempt < HTTP_RETRIES:
                _backoff_sleep(attempt)
            continue

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                # chat 正常走 HTTP 状态码，这里只是对 200+error 体做兜底
                raise GenerationError(f"API 返回错误体：{data['error']}")
            if not (data.get("choices")):
                raise GenerationError(f"响应缺少 choices：{str(data)[:300]}")
            return data

        body = resp.text[:300]
        if resp.status_code == 429 and "1113" in body:
            # 余额不足 / 套餐 Key 打错端点：重试无意义，把两种成因都说清楚
            raise GenerationError(
                f"HTTP 429 / 错误码 1113（余额不足或无可用资源包）：{body}。"
                "注意：GLM Coding Plan 套餐 Key 不能打标准端点 …/api/paas/v4，"
                "请改用标准 API Key 的 ZHIPUAI_API_KEY，或换套餐端点。"
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"HTTP {resp.status_code}：{body}"
            if attempt < HTTP_RETRIES:
                _backoff_sleep(attempt)
            continue
        # 400/401/403 等配置类错误：重试没有意义
        raise GenerationError(f"HTTP {resp.status_code}（配置/参数错误，不重试）：{body}")

    raise GenerationError(f"请求连续 {HTTP_RETRIES} 次失败，最后错误：{last_err}")


# ---------------------------------------------------------------- 生成流程

def generate_once(api_key, messages):
    """跑一遍多轮生成，处理 finish_reason=length 的自动续写。

    只有最终 finish_reason=stop（自然收尾）的文本才算合格成品；
    sensitive / network_error 等异常终止直接抛错，由上层整篇重试。
    返回 (全文, 请求轮数)。
    """
    parts = []
    rounds = 0
    while True:
        rounds += 1
        data = chat_completion(api_key, messages)
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        piece = (choice.get("message") or {}).get("content") or ""
        parts.append(piece)

        if finish == "stop":
            return "".join(parts), rounds
        if finish == "length":
            if rounds >= MAX_CONTINUE_ROUNDS:
                raise GenerationError(
                    f"连续续写 {rounds} 轮仍被 max_tokens 截断，放弃该稿"
                )
            # 把半截正文作为 assistant 历史回传，让模型从中断处接着写
            messages = messages + [
                {"role": "assistant", "content": piece},
                {"role": "user", "content": CONTINUE_PROMPT},
            ]
            continue
        # sensitive / network_error / model_context_window_exceeded 等
        raise GenerationError(
            f"本轮生成异常终止（finish_reason={finish}），放弃该稿；"
            f"已生成内容不会作为成品输出"
        )


def build_report(api_key):
    """生成 + 校验 + 不达标重写，返回 (合格全文, 请求轮数, 第几稿)。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]
    for attempt in range(1, MAX_DRAFT_ATTEMPTS + 1):
        try:
            report, rounds = generate_once(api_key, messages)
        except GenerationError as exc:
            print(f"[warn] 第 {attempt} 稿生成失败：{exc}", file=sys.stderr)
            messages = [  # 整篇重试回到初始指令
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ]
            continue

        issues = validate(report)
        if not issues:
            return report, rounds, attempt
        print(f"[warn] 第 {attempt} 稿未通过校验：{'；'.join(issues)}，重写", file=sys.stderr)
        messages = [  # 带着问题清单让模型重写整篇
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": REPAIR_PROMPT_TEMPLATE.format(
                issues="\n".join(f"- {i}" for i in issues),
                draft=report,
            )},
        ]
    raise GenerationError(
        f"连续 {MAX_DRAFT_ATTEMPTS} 稿均未产出合格简报，已放弃；"
        "为避免交付残缺内容，本次不输出任何稿件全文"
    )


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台标准 API Key）",
              file=sys.stderr)
        return 2

    try:
        report, rounds, attempt = build_report(api_key)
    except GenerationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    sep = "=" * 22
    print(f"{sep} 简报全文 {sep}")
    print(report.strip())
    print(sep * 2 + "==")

    n = count_chars(report)
    s = count_sections(report)
    print()
    print("【交付校验】")
    print(f"- 字数：正文 {n} 字（不含空白字符），要求 ≥ {MIN_BODY_CHARS} 字"
          f" → {'✅ 达标' if n >= MIN_BODY_CHARS else '❌ 不达标'}")
    print(f"- 小标题：{s} 个 Markdown 标题，要求 ≥ {MIN_SECTIONS} 个"
          f" → {'✅ 达标' if s >= MIN_SECTIONS else '❌ 不达标'}")
    print(f"- 具体数据：{'✅ 全文含数字型数据' if has_data(report) else '❌ 缺失'}")
    print(f"- 完整性：✅ finish_reason=stop 自然收尾（含续写共 {rounds} 轮请求，"
          f"第 {attempt} 稿通过），末句收束完整")
    print()

    # build_report 已保证过校验，这里再独立复核一次，双双通过才宣称可交付
    if not validate(report):
        print(f"✅ 确认：简报完整且字数达标（{n} 字 ≥ {MIN_BODY_CHARS} 字），可直接进入周报。")
        return 0
    print("❌ 复核未通过，拒绝交付（不应发生）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
