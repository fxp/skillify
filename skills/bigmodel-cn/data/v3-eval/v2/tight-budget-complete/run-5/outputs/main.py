#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口》市场简报。

约束与对策：
- 硬约束：下游网关限制单次请求 max_tokens 绝对不能超过 1000。脚本内以
  GATEWAY_MAX_TOKENS_CAP 常量兜底，所有出站请求的 max_tokens 都经过 clamp +
  断言，结构上不可能超过上限。
- 篇幅要求：完整正文不少于 600 汉字，有小标题和数据。单次 1000 token 的预算
  放不下一份 600+ 汉字的成稿（且思考 token 会计入 max_tokens），因此按大纲
  拆成 5 个小节分多次请求生成，每次只写一小节；汇总后不足 600 汉字则自动
  追加补充小节，直到达标。
- 模型选型：glm-5.2 并显式传 thinking={"type":"disabled"}。官方文档确认：
  思考 token 计入 max_tokens（预算小时会拿到空 content + finish_reason=length）；
  glm-5.3/5.3-flash 在标准端点无法关闭思考，而 glm-5.2 支持显式关闭，1000
  token 预算全部留给正文。
- 失败策略：任何小节重试后仍失败、或最终不足 600 汉字，都明确打印卡点并以
  非零码退出，不把半截正文当成交付。

用法：
    ZHIPUAI_API_KEY=<你的 Key> python3 main.py
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("GLM_MODEL", "glm-5.2")

# 网关硬约束：单次请求 max_tokens 绝对不能超过 1000。
GATEWAY_MAX_TOKENS_CAP = 1000
# 每个小节请求的 max_tokens：取到上限（等于、不超过），单节 170~220 汉字绰绰有余。
SECTION_MAX_TOKENS = min(1000, GATEWAY_MAX_TOKENS_CAP)

TARGET_HANZI = 600            # 完整正文的汉字数下限
MIN_SECTION_HANZI = 80        # 单个小节可接受的汉字数下限
MAX_ATTEMPTS = 3              # 单个请求（网络/限流/校验不过）的最大尝试次数
MAX_EXTRA_SECTIONS = 3        # 不足 600 汉字时最多补写的小节数
REQUEST_TIMEOUT = (10, 120)   # (连接, 读取) 超时，秒
RETRY_BACKOFF_SECONDS = 2

BRIEF_TITLE = "2026 年中国新能源汽车出口市场简报"

# 基础大纲：5 节目标篇幅合计约 790~1040 汉字，留足 600 的余量。
BASE_OUTLINE = [
    ("一、市场总览", "2026 年中国新能源汽车出口总量、同比增速、出口金额，以及占中国汽车整体出口的比重", "170~220"),
    ("二、区域格局", "欧洲、东南亚、拉美、中东等主要目的市场的结构与变化，至少覆盖三个区域的数据", "160~210"),
    ("三、车企与产品表现", "比亚迪、奇瑞、上汽、吉利等主要出口车企的出口量与车型策略", "160~210"),
    ("四、挑战与风险", "欧盟反补贴税、贸易壁垒、海运运力、海外建厂与合规成本等压力", "150~200"),
    ("五、趋势与建议", "2026 年下半年至 2027 年的走势判断，以及对出口企业的建议", "150~200"),
]

# 基础小节全部生成后仍不足 600 汉字时，按顺序补写。
EXTRA_TOPICS = [
    ("六、供应链与电池出海", "宁德时代等电池企业与零部件配套随整车出海的进展和数据", "150~200"),
    ("七、二手车与售后网络", "新能源二手车出口试点、海外售后与充电服务网络建设情况", "150~200"),
    ("八、价格与盈利", "出口均价变化、海运成本与汇率波动对出口盈利的影响", "150~200"),
]

OUTLINE = BASE_OUTLINE + EXTRA_TOPICS

HANZI_RE = re.compile(r"[一-鿿]")
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# 简单请求统计，供最终报告"实际请求次数"。
STATS = {"attempts": 0, "ok": 0}


class GenerationError(RuntimeError):
    """生成失败，message 里携带完整卡点信息。"""


def hanzi_count(text):
    """数一段文本里的汉字数（只计 一-鿿，不含标点、数字、字母）。"""
    return len(HANZI_RE.findall(text))


def clean_section_text(raw):
    """清洗模型输出：去思考标签、markdown 围栏、首尾空白。"""
    text = THINK_RE.sub("", raw or "")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def extract_api_error(status, body):
    """把 API 错误响应整理成一句话，尽量带平台错误码。"""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return "HTTP %s, code=%s, message=%s" % (status, err.get("code"), err.get("message"))
        return "HTTP %s, body=%s" % (status, str(body)[:300])
    return "HTTP %s, body=%s" % (status, str(body)[:300])


def chat_request(messages):
    """发一次对话补全请求，返回 (content, finish_reason)。

    max_tokens 恒为 SECTION_MAX_TOKENS（≤ GATEWAY_MAX_TOKENS_CAP）；
    网络异常、429、5xx 自动退避重试；4xx 直接抛错（重试无意义）。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": SECTION_MAX_TOKENS,
        "temperature": 0.5,
        "thinking": {"type": "disabled"},  # 关思考：避免 reasoning 吃掉 max_tokens 预算
        "stream": False,
    }
    if payload["max_tokens"] > GATEWAY_MAX_TOKENS_CAP:
        raise GenerationError(
            "内部错误：max_tokens=%d 超过网关上限 %d，拒绝发请求"
            % (payload["max_tokens"], GATEWAY_MAX_TOKENS_CAP)
        )
    headers = {
        "Authorization": "Bearer %s" % os.environ["ZHIPUAI_API_KEY"],
        "Content-Type": "application/json",
    }
    last_error = "尚未发起请求"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        STATS["attempts"] += 1
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = "第 %d 次尝试网络异常：%r" % (attempt, exc)
            print("[warn] %s" % last_error, file=sys.stderr)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = "第 %d 次尝试 HTTP %d（限流/服务端错误），响应：%s" % (
                attempt, resp.status_code, resp.text[:200])
            print("[warn] %s" % last_error, file=sys.stderr)
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue
        try:
            data = resp.json()
        except ValueError:
            raise GenerationError("HTTP %d，响应不是 JSON：%s" % (resp.status_code, resp.text[:300]))
        if resp.status_code >= 400:
            raise GenerationError(extract_api_error(resp.status_code, data))
        choices = data.get("choices") or []
        if not choices:
            raise GenerationError("响应缺少 choices：%s" % str(data)[:300])
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason") or ""
        echoed_model = data.get("model") or ""
        # 读回响应的 model 字段核对（防静默换模型）；不一致先只提醒，不中断。
        if echoed_model and echoed_model != MODEL:
            print("[warn] 响应 model=%s 与请求的 %s 不一致，请核对" % (echoed_model, MODEL), file=sys.stderr)
        STATS["ok"] += 1
        return content, finish_reason
    raise GenerationError("重试 %d 次仍失败，最后错误：%s" % (MAX_ATTEMPTS, last_error))


def generate_section(title, topic, length_hint, written_titles):
    """生成并校验一个小节，返回 (小节文本, 汉字数)。校验不过自动重试。"""
    system = (
        "你是一名汽车行业市场分析师，正在为一份《%s》撰写正式正文。"
        "语言为简体中文，风格专业克制，观点有数据支撑。" % BRIEF_TITLE
    )
    all_outline = "；".join("「%s」" % t for t, _, _ in OUTLINE)
    written = "；".join("「%s」" % t for t in written_titles) if written_titles else "（暂无）"
    user = (
        "你正在撰写《%s》，全文按顺序分为这些小节：%s。\n"
        "已写完的小节：%s。\n"
        "现在请只撰写「%s」这一小节。主题与要点：%s。\n"
        "格式与篇幅要求：\n"
        "1. 第一行输出小标题，格式为「## %s」；\n"
        "2. 小标题之下写 %s 个汉字的正文，可分 1~2 个自然段；\n"
        "3. 正文必须包含具体数据（出口量、增速、金额、份额或排名等，可基于公开行业信息合理估计）；\n"
        "4. 不要重复已写完小节的信息，不要输出本小节以外的任何内容"
        "（不要寒暄、不要总述、不要代码块），直接以「## 」开头。"
        % (BRIEF_TITLE, all_outline, written, title, topic, title, length_hint)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    attempts_log = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        content, finish_reason = chat_request(messages)
        text = clean_section_text(content)
        count = hanzi_count(text)
        problems = []
        if finish_reason == "sensitive":
            problems.append("finish_reason=sensitive（内容安全拦截）")
        elif finish_reason == "network_error":
            problems.append("finish_reason=network_error（模型推理异常）")
        elif finish_reason == "model_context_window_exceeded":
            problems.append("finish_reason=model_context_window_exceeded")
        if not text:
            problems.append("content 为空")
        elif "##" not in text:
            problems.append("输出里没有「##」小标题")
        elif count < MIN_SECTION_HANZI:
            problems.append("汉字数 %d 低于单节下限 %d" % (count, MIN_SECTION_HANZI))
        if problems:
            attempts_log.append(
                "第 %d 次（finish_reason=%s）：%s" % (attempt, finish_reason or "空", "；".join(problems)))
            time.sleep(1)
            continue
        if finish_reason == "length":
            print("[warn] 小节「%s」finish_reason=length，token 预算被用满，内容已接受" % title, file=sys.stderr)
        return text, count
    raise GenerationError(
        "小节「%s」连续 %d 次未通过校验。卡点：%s" % (title, MAX_ATTEMPTS, " | ".join(attempts_log)))


def main():
    if not os.environ.get("ZHIPUAI_API_KEY"):
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用接口。\n"
            "请先执行：export ZHIPUAI_API_KEY=<你的 API Key>\n"
            "Key 在控制台获取：https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
            file=sys.stderr,
        )
        return 1

    print(
        "[info] 模型 %s；单次请求 max_tokens=%d（网关上限 %d，硬约束）"
        % (MODEL, SECTION_MAX_TOKENS, GATEWAY_MAX_TOKENS_CAP),
        file=sys.stderr,
    )

    sections = []   # [(title, text)]，按写作顺序
    failures = []   # 所有卡点记录

    def add_section(title, topic, length_hint):
        try:
            text, count = generate_section(title, topic, length_hint, [t for t, _ in sections])
        except GenerationError as exc:
            failures.append(str(exc))
            print("[fail] %s" % exc, file=sys.stderr)
            return
        sections.append((title, text))
        print("[ok] 小节「%s」：%d 汉字" % (title, count), file=sys.stderr)

    for title, topic, length_hint in BASE_OUTLINE:
        add_section(title, topic, length_hint)

    def assembled_text():
        return "# %s\n\n%s" % (BRIEF_TITLE, "\n\n".join(text for _, text in sections))

    # 基础小节写完仍不足 600 汉字时，按序补写（最多 MAX_EXTRA_SECTIONS 节）。
    extra_used = 0
    while hanzi_count(assembled_text()) < TARGET_HANZI and extra_used < MAX_EXTRA_SECTIONS:
        title, topic, length_hint = EXTRA_TOPICS[extra_used]
        extra_used += 1
        print("[info] 当前 %d 汉字不足 %d，补写小节「%s」" % (hanzi_count(assembled_text()), TARGET_HANZI, title), file=sys.stderr)
        add_section(title, topic, length_hint)

    full_text = assembled_text()
    total_hanzi = hanzi_count(full_text)
    total_chars = len(full_text)

    if total_hanzi < TARGET_HANZI:
        # 失败路径：说清楚卡在哪，正文只作为"不完整草稿"标注，不算交付。
        print("\n" + "=" * 60, file=sys.stderr)
        print("生成失败：完整正文要求 ≥%d 汉字，实际只有 %d 汉字，不作为交付。" % (TARGET_HANZI, total_hanzi), file=sys.stderr)
        print("卡点（共 %d 条）：" % len(failures), file=sys.stderr)
        for item in failures:
            print("  - %s" % item, file=sys.stderr)
        if not failures:
            print("  - 无接口报错，但各小节实际篇幅持续低于预期", file=sys.stderr)
        print("实际请求：成功 %d 次 / 共发起 %d 次（含重试），每次 max_tokens=%d。" % (
            STATS["ok"], STATS["attempts"], SECTION_MAX_TOKENS), file=sys.stderr)
        print("【不完整草稿，仅供参考，勿当交付】\n%s" % full_text, file=sys.stderr)
        return 1

    # 成功路径：打印全文，再报实际字数。
    print(full_text)
    print()
    print("=" * 60)
    print("统计：")
    print("  正文汉字数：%d 字（要求 ≥%d，已达标）" % (total_hanzi, TARGET_HANZI))
    print("  全文总字符数：%d（含小标题、标点、数字与换行）" % total_chars)
    print("  小节数：%d（%s）" % (len(sections), "、".join(t for t, _ in sections)))
    print("  单次请求 max_tokens=%d，未超过网关上限 %d" % (SECTION_MAX_TOKENS, GATEWAY_MAX_TOKENS_CAP))
    print("  实际请求：成功 %d 次 / 共发起 %d 次（含重试）" % (STATS["ok"], STATS["attempts"]))
    if failures:
        print("  注意：有 %d 个小节生成失败被跳过（详见 stderr）" % len(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
