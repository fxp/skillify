# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口市场简报》。

约束与策略：
- 下游网关硬约束：单次请求 max_tokens 绝对不能超过 1000。
  因此不一次性生成全文，而是按小标题分节多次请求（每节目标约 150 汉字，
  官方口径 1 token ≈ 1.5 个汉字，单节输出远小于上限），
  逐节校验 finish_reason == "stop"，最后拼装并统计正文字数。
- 模型选 glm-4.6 并显式 thinking.type=disabled：
  glm-5.3 在标准端点强制思考，且思考 token 计入 max_tokens，
  会挤占本就紧张的输出预算（SKILL 实测坑 #13/#14）。
- 任何一节失败即整体失败并报出卡点，绝不输出半截正文。
- 依赖：仅 requests；密钥从环境变量 ZHIPUAI_API_KEY 读取。

用法：python3 main.py
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"

HARD_TOKEN_CAP = 1000        # 网关硬上限，任何请求不得突破
MAX_TOKENS_PER_REQUEST = 800  # 实际请求值，留安全余量
TARGET_BODY_CHARS = 600      # 正文（不含标题）汉字数下限
SECTION_TARGET = 150         # 每节目标汉字数
MAX_EXPAND_ROUNDS = 3        # 字数不足时的补写轮数上限
HTTP_RETRIES = 3             # 网络/限流重试次数

REPORT_TITLE = "2026 年中国新能源汽车出口市场简报"

# 简报骨架：小标题 + 该节必须给出的数据点（固定骨架，保证结构与数据密度）
SECTIONS = [
    ("一、总量与增速",
     "2026 年中国新能源汽车出口整车预计规模（万辆）、同比增速、"
     "新能源占汽车整体出口的比重，以及较 2024/2025 年的变化趋势"),
    ("二、区域市场结构",
     "前三大海外市场（如欧洲、东南亚、拉美/中东）各自占比或增速，"
     "至少给出两个区域的具体数字与一个新兴高增长市场"),
    ("三、品牌与车型格局",
     "头部出口企业（如比亚迪、奇瑞、上汽、吉利等）出口量或份额数据，"
     "插混与纯电两条路线的占比变化"),
    ("四、出口方式与本地化",
     "滚装海运运力与运价变化、海外本地化建厂/组装的产能数字、"
     "本地化生产对整车出口的分流影响"),
    ("五、风险与挑战",
     "欧盟反补贴关税税率区间、其他市场贸易壁垒、运力与汇率成本等"
     "至少两类量化风险"),
    ("六、2027 年展望",
     "对 2027 年出口量的预测区间、增速假设、以及结构性机会"
     "（如插混、右舵市场、新兴市场渗透率）"),
]


class BriefError(Exception):
    """携带阶段信息的失败，用于向用户报出"卡在哪"。"""


def chat(label, user_prompt, max_tokens):
    """同步调用 chat/completions，带硬上限校验、重试与完整错误定位。"""
    if max_tokens > HARD_TOKEN_CAP:
        raise BriefError(f"[{label}] 内部错误：max_tokens={max_tokens} 超过硬上限 {HARD_TOKEN_CAP}")

    headers = {
        "Authorization": f"Bearer {os.environ['ZHIPUAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},  # 关闭思考，输出预算全部留给正文
        "temperature": 0.6,
    }

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}（第 {attempt} 次尝试）"
                time.sleep(2 * attempt)
                continue
            if resp.status_code != 200:
                raise BriefError(f"[{label}] HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                body = resp.json()
            except ValueError:
                last_err = f"HTTP 200 但响应不是 JSON: {resp.text[:200]}"
                time.sleep(2 * attempt)
                continue
            break
        except requests.RequestException as exc:
            last_err = f"网络异常 {exc.__class__.__name__}: {exc}"
            time.sleep(2 * attempt)
    else:
        raise BriefError(f"[{label}] 重试 {HTTP_RETRIES} 次仍失败：{last_err}")

    err = body.get("error")
    if err:
        raise BriefError(f"[{label}] 平台返回错误 code={err.get('code')}: {err.get('message')}")

    try:
        choice = body["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        finish = choice.get("finish_reason")
        usage = body.get("usage", {})
    except (KeyError, IndexError, TypeError) as exc:
        raise BriefError(f"[{label}] 响应结构异常（{exc}）: {str(body)[:300]}")

    USAGE_LOG.append({
        "label": label,
        "max_tokens": max_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "finish_reason": finish,
        "model": body.get("model", MODEL),
    })

    # finish_reason 判据（SKILL 坑 #13）：length=被 max_tokens 截断，sensitive=审核拦截
    if finish == "length":
        raise BriefError(
            f"[{label}] finish_reason=length：本节输出撞到 max_tokens={max_tokens} 被截断，"
            f"completion_tokens={usage.get('completion_tokens')}。该节不达标，整体终止以免给半截。")
    if finish == "sensitive":
        raise BriefError(f"[{label}] finish_reason=sensitive：内容被安全审核拦截。")
    if finish not in ("stop", None):
        raise BriefError(f"[{label}] finish_reason={finish}：异常结束。")
    if not content:
        raise BriefError(f"[{label}] 返回内容为空（finish_reason={finish}）。")
    return content


def gen_section(index, title, data_points, target_chars):
    """生成一节正文，输出只含正文段落（无小标题、无换行）。"""
    label = f"第 {index + 1} 节 {title}"
    prompt = (
        f"你是一名汽车行业分析师，正在撰写《{REPORT_TITLE}》中标题为「{title}」的一节。"
        f"要求：\n"
        f"1. 只写这一节的正文段落，直接输出连续的一段话，不要输出小标题，不要换行，"
        f"不要使用任何 Markdown 标记、列表或引号；\n"
        f"2. 正文长度约 {target_chars - 20}~{target_chars + 50} 个汉字；\n"
        f"3. 必须包含具体数据（数字、百分比或金额），围绕以下要点展开：{data_points}；\n"
        f"4. 数据为基于公开行业信息的估算口径，表述自然、口径一致。"
    )
    text = chat(label, prompt, MAX_TOKENS_PER_REQUEST)
    # 轻度清洗：模型偶尔仍会带上标题行或换行
    text = re.sub(r"\s+", "", text)
    text = text.strip("“”\"' 　")
    return text


def count_han(text):
    return len(re.findall(r"[一-鿿]", text))


def main():
    if not os.environ.get("ZHIPUAI_API_KEY"):
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱开放平台。", file=sys.stderr)
        print("请先执行：export ZHIPUAI_API_KEY=<你的 Key>", file=sys.stderr)
        sys.exit(2)

    paragraphs = []
    # 逐节生成；任何一节失败都会抛 BriefError，直接终止，不输出半截
    for i, (title, points) in enumerate(SECTIONS):
        para = gen_section(i, title, points, SECTION_TARGET)
        paragraphs.append((title, para))
        print(f"· {title} 完成（{count_han(para)} 汉字）", file=sys.stderr)

    # 字数兜底：正文不足 600 汉字时，对最短的一节定向扩写（仍受单请求上限约束）
    expand_round = 0
    while sum(count_han(p) for _, p in paragraphs) < TARGET_BODY_CHARS:
        if expand_round >= MAX_EXPAND_ROUNDS:
            break
        expand_round += 1
        i, (title, para) = min(enumerate(paragraphs), key=lambda t: count_han(t[1][1]))
        need = TARGET_BODY_CHARS - sum(count_han(p) for _, p in paragraphs)
        prompt = (
            f"以下是《{REPORT_TITLE}》中「{title}」一节的现有正文：\n{para}\n"
            f"请在保留原有信息与数据的基础上扩写，至少补充 {need + 30} 个汉字，"
            f"补充内容需新增具体数据点。只输出扩写后的完整段落，不要小标题、"
            f"不要换行、不要 Markdown。"
        )
        new_para = re.sub(r"\s+", "", chat(f"扩写 {title}", prompt, MAX_TOKENS_PER_REQUEST))
        paragraphs[i] = (title, new_para)
        print(f"· 第 {expand_round} 轮扩写：{title} → {count_han(new_para)} 汉字", file=sys.stderr)

    body_chars = sum(count_han(p) for _, p in paragraphs)

    # ============ 打印全文 ============
    print("=" * 46)
    print(REPORT_TITLE)
    print("=" * 46)
    for title, para in paragraphs:
        print(f"\n{title}\n{para}")
    print("\n注：文中数据为模型基于公开行业信息生成的估算口径，供参考。")
    print("=" * 46)

    # ============ 字数与合规报告 ============
    print(f"\n正文汉字数（不含标题与注释行）：{body_chars}")
    if body_chars >= TARGET_BODY_CHARS:
        print(f"达标：正文汉字数 {body_chars} ≥ 要求 {TARGET_BODY_CHARS}。")
    else:
        print(f"未达标：{body_chars} < {TARGET_BODY_CHARS}，"
              f"已扩写 {expand_round} 轮仍不足，判定失败，不交付半截正文。")
        sys.exit(1)

    print(f"\n单请求合规审计（硬上限 max_tokens ≤ {HARD_TOKEN_CAP}）：")
    for row in USAGE_LOG:
        assert row["max_tokens"] <= HARD_TOKEN_CAP
        print(f"  - {row['label']}: max_tokens={row['max_tokens']}, "
              f"completion_tokens={row['completion_tokens']}, "
              f"finish_reason={row['finish_reason']}, 实际模型={row['model']}")
    print(f"共 {len(USAGE_LOG)} 次请求，全部满足单请求 max_tokens ≤ {HARD_TOKEN_CAP}。")


USAGE_LOG = []

if __name__ == "__main__":
    try:
        main()
    except BriefError as exc:
        print(f"\n生成失败，卡点如下：\n{exc}", file=sys.stderr)
        print("按约定不输出半截正文。请排查上述环节后重试。", file=sys.stderr)
        sys.exit(1)
