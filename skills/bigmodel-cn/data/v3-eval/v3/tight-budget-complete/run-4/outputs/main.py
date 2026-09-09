#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口》市场简报（不少于 600 汉字，含小标题与数据）。

下游网关硬约束：单次请求 max_tokens 绝对不能超过 1000。
因此本脚本刻意不做"一次请求生成全文"，原因（均为平台实测行为）：

1. 思考 token 计入 max_tokens：600 字简报的思维链就要 2400+ token，
   1000 的预算会被推理吃光——HTTP 200、不报错、finish_reason=length、
   正文为空。判据是 finish_reason，不是"没报错"。
2. glm-5.3 在标准端点强制思考，thinking.type=disabled 会报 1210；
   故模型选 glm-5.2，标准端点支持显式关闭思考。
3. 即使关掉思考，600+ 汉字一次成型也约需 1500 token，仍超预算；
   故拆成 4 个小节分段生成、本地拼接，每次请求 max_tokens 固定 1000。

兜底策略（检测到问题不直接丢半截退出）：
- finish_reason=length：不加预算（硬约束不可突破），改用更精简的指令重试，
  并把截断文本裁到完整句子作为候补；
- 全文不足 600 汉字：自动追加补充段，单次请求仍不超过 1000；
- 重试耗尽仍不达标：打印卡住的具体环节与原因，退出码 1，不输出半截正文。

用法：ZHIPUAI_API_KEY 需从环境变量读取，python3 main.py 直接运行。
依赖：仅 requests + 标准库。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.2"  # 标准端点可用 thinking.type=disabled 显式关思考（glm-5.3 不行，报 1210）

# ── 网关硬约束：单次请求 max_tokens 上限，任何请求都经 chat() 夹紧到这里 ──
HARD_CAP = 1000
MAX_TOKENS_PER_REQUEST = 1000  # 恒 <= HARD_CAP

TARGET_HAN = 600        # 正文汉字数下限
SECTION_ATTEMPTS = 3    # 单个小节的生成尝试次数
HTTP_RETRIES = 3        # 单次请求的网络/5xx 重试次数
HTTP_TIMEOUT = 90

HAN_RE = re.compile(r"[一-鿿]")
SENTENCE_END = "。！？；"

SESSION = requests.Session()
REQUEST_COUNT = 0  # 实际发起的请求次数，最后随字数一并报告


def count_han(text: str) -> int:
    """统计汉字数（数字、字母、标点不计入，避免用水分凑数）。"""
    return len(HAN_RE.findall(text))


def trim_to_sentence(text: str) -> str:
    """把截断文本裁到最后一个完整句子，避免交付半句话。"""
    cut = max(text.rfind(c) for c in SENTENCE_END)
    return text[: cut + 1] if cut >= 0 else text


def _error_detail(resp) -> str:
    """平台业务错误码在 body.error 里，原样带出来便于定位。"""
    try:
        err = resp.json().get("error") or resp.json()
        return f"{err.get('code')} {err.get('message')}"
    except Exception:
        return resp.text[:200]


def chat(messages, temperature=0.3):
    """发起一次对话补全。max_tokens 只在这里组装，恒为 MAX_TOKENS_PER_REQUEST（<=1000）。

    返回 (content, finish_reason, usage)；网络/5xx 重试耗尽或 4xx 业务错时抛 RuntimeError。
    """
    global REQUEST_COUNT
    if MAX_TOKENS_PER_REQUEST > HARD_CAP:
        raise RuntimeError(f"max_tokens={MAX_TOKENS_PER_REQUEST} 超过网关硬上限 {HARD_CAP}")
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS_PER_REQUEST,
        "temperature": temperature,
        # 关键：显式关闭思考，让 1000 token 预算全部留给正文（见文件头说明第 1/2 条）
        "thinking": {"type": "disabled"},
    }
    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            REQUEST_COUNT += 1
            resp = SESSION.post(API_URL, headers=SESSION.headers, json=payload, timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                detail = _error_detail(resp)
                last_err = f"HTTP {resp.status_code}: {detail}"
                if resp.status_code >= 500 or resp.status_code == 429:
                    time.sleep(2 * attempt)  # 限流/服务端抖动，退避后重试
                    continue
                raise RuntimeError(last_err)  # 4xx 参数/鉴权错，重试没有意义
            data = resp.json()
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
            finish = choice.get("finish_reason")
            echoed = data.get("model", MODEL)
            if echoed != MODEL:
                # 同步端点按实测不换模型；真被换了要留痕，便于对账
                print(f"[warn] 服务端实际运行模型为 {echoed}（请求为 {MODEL}）", file=sys.stderr)
            return content.strip(), finish, data.get("usage", {})
        except requests.RequestException as exc:
            last_err = f"网络异常: {exc!r}"
            time.sleep(2 * attempt)
    raise RuntimeError(f"连续 {HTTP_RETRIES} 次请求失败，最后一次: {last_err}")


class SectionError(RuntimeError):
    """单个小节重试耗尽仍不可用。"""


def generate_section(title: str, brief: str, hi: int = 220) -> str:
    """生成一个小节正文（不含标题）。返回能拿到的最佳文本；彻底失败抛 SectionError。

    finish_reason=length 时不加预算（硬约束），而是逐次收紧字数要求重试；
    截断文本裁到完整句子后作为候补，取汉字数最多者。
    """
    system = (
        "你是一名汽车行业市场分析师，为面向管理层的市场简报撰稿。"
        "要求观点凝练、必须给出具体数字（无公开数据处用合理估计并标注\"约\"），不写套话。"
    )
    best, diag = "", []
    for attempt in range(1, SECTION_ATTEMPTS + 1):
        hi_try = hi - 30 * (attempt - 1)  # 220 -> 190 -> 160，被截断就要求更短
        lo_try = max(120, hi_try - 60)
        squeeze = "" if attempt == 1 else f"注意：上一次在 token 预算内没写完，这次务必控制在 {lo_try}~{hi_try} 字。"
        user = (
            f"请为市场简报撰写小节《{title}》的正文。\n"
            f"内容要点：{brief}\n"
            f"硬性要求：\n"
            f"- 只输出这一小节的正文，禁止输出标题、编号、开场白和总结语；\n"
            f"- 长度 {lo_try}~{hi_try} 个汉字；\n"
            f"- 至少包含 3 个具体数字（出口量、增速、占比、金额等）；\n"
            f"- 用连贯段落陈述，不要使用列表。\n{squeeze}"
        )
        try:
            content, finish, usage = chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}]
            )
        except RuntimeError as exc:
            diag.append(f"第 {attempt} 次尝试: {exc}")
            continue

        if finish == "length":
            # 预算内没写完。不加 max_tokens（网关硬上限），换更短的要求重试；
            # 已有部分裁到完整句子留作候补，不直接丢弃。
            cand = trim_to_sentence(content)
            diag.append(
                f"第 {attempt} 次尝试: finish_reason=length（max_tokens={MAX_TOKENS_PER_REQUEST} 内未写完，"
                f"拿到 {count_han(cand)} 汉字，已裁到完整句）"
            )
        elif not content:
            diag.append(f"第 {attempt} 次尝试: finish_reason={finish} 但 content 为空")
            continue
        else:
            cand = content

        if count_han(cand) > count_han(best):
            best = cand
        if finish == "stop" and count_han(best) >= 80:
            return best

    if count_han(best) >= 60:
        print(f"[warn] 小节《{title}》未拿到理想长度，使用截断裁剪后的候补文本", file=sys.stderr)
        return best
    raise SectionError(f"小节《{title}》生成失败:\n  " + "\n  ".join(diag))


# ── 简报结构：4 个小节，每节单独一次请求，正文目标 160~220 汉字，合计下限远超 600 ──
SECTIONS = [
    (
        "一、出口总量与增速",
        "2026 年中国新能源汽车出口总量：全年或前三个季度出口量（万辆）、同比增速、"
        "出口金额（亿元或美元）、新能源汽车占汽车整体出口的比重变化。",
    ),
    (
        "二、区域市场格局",
        "分区域表现：欧洲（含欧盟关税影响）、拉美、东南亚、中东、澳新等市场的"
        "销量或占比与同比变化，重点新兴市场的突破情况。",
    ),
    (
        "三、竞争格局与头部车企",
        "头部车企出口表现：比亚迪、奇瑞、上汽、吉利、长城等的出口量、市场份额、"
        "主力车型与出口均价区间。",
    ),
    (
        "四、挑战与全年展望",
        "当前挑战：关税与贸易壁垒、本地化生产要求、海运运力与汇率波动；"
        "对 2026 全年出口量的预测，以及插混/纯电结构、海外建厂等趋势判断。",
    ),
]

# 正文不足 600 汉字时的补充段主题（每次补充仍是一次独立请求，max_tokens 不变）
EXTRA_TOPICS = [
    "动力电池与零部件供应链随整车出海的进展及代表企业布局",
    "海外充电标准适配、售后服务网络与品牌建设的投入情况",
    "二手车出口、出口金融与保险等配套体系的最新发展",
]


def assemble(parts) -> str:
    head = "# 2026 年中国新能源汽车出口市场简报\n\n（数据由大模型生成，供内部参考）\n\n"
    return head + "\n\n".join(f"## {t}\n\n{p}" for t, p in parts)


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "[失败] 环境变量 ZHIPUAI_API_KEY 未设置，无法调用智谱 API。\n"
            "请先执行: export ZHIPUAI_API_KEY=<你的 Key> 再运行 python3 main.py",
            file=sys.stderr,
        )
        sys.exit(1)
    SESSION.headers.update({"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    # 1) 分段生成四个小节（每段一次请求，max_tokens=1000）
    parts, failures = [], []
    for title, brief in SECTIONS:
        try:
            parts.append((title, generate_section(title, brief)))
        except SectionError as exc:
            failures.append(str(exc))

    # 2) 拼接后仍不足 600 汉字则追加补充段，不突破单次预算
    extra_used = 0
    for topic in EXTRA_TOPICS:
        if count_han(assemble(parts)) >= TARGET_HAN:
            break
        try:
            para = generate_section("行业补充观察", topic, hi=180)
            if extra_used == 0:
                parts.append(("五、行业补充观察", para))
            else:
                parts[-1] = (parts[-1][0], parts[-1][1].rstrip("。") + "。" + para)
            extra_used += 1
        except SectionError as exc:
            failures.append(str(exc))

    text = assemble(parts)
    han = count_han(text)

    # 3) 达标：打印全文 + 实际字数；不达标：说清卡在哪，不交付半截正文
    if han < TARGET_HAN:
        where = "\n".join(failures) if failures else "各小节均正常返回，但模型单段输出偏短"
        print(
            f"[失败] 简报未达到 {TARGET_HAN} 汉字要求（当前正文 {han} 汉字），"
            f"不输出半截结果。卡点如下：\n{where}\n"
            f"共发起 {REQUEST_COUNT} 次请求，单次 max_tokens={MAX_TOKENS_PER_REQUEST}。"
            f"建议检查：ZHIPUAI_API_KEY 有效性、账户余额/限流，或适当调大 TARGET_HAN 以外的重试参数。",
            file=sys.stderr,
        )
        sys.exit(1)

    print(text)
    print("\n" + "=" * 60)
    print(f"正文汉字数：{han}（要求 ≥ {TARGET_HAN}）")
    print(f"全文总字符数：{len(text)}")
    print(f"共发起 {REQUEST_COUNT} 次请求，单次 max_tokens 恒为 {MAX_TOKENS_PER_REQUEST}（网关上限 {HARD_CAP}，未超）")


if __name__ == "__main__":
    main()
