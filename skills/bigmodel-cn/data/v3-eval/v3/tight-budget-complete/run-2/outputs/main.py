#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口》市场简报（不少于 600 汉字，含小标题与数据）。

网关硬约束：单次请求的 max_tokens 绝对不能超过 1000，不可协商。

应对策略（依据 bigmodel-cn 技能包的实测结论）：
  1. 速查表 #13：思考 token 计入 max_tokens，小预算下会 finish_reason=length
     且正文为空。因此选用 glm-4.6——官方文档确认其在标准端点支持
     thinking.type=disabled（glm-5.3 在标准端点强制思考关不掉，见 #14），
     每次请求显式关思考，把 1000 以内的预算全部留给正文。
  2. 补救表第 ③ 招：分段生成再拼接。全文拆成 5 个小节，每节一次独立请求，
     单节目标约 180~200 汉字，5 节合计约 950 汉字，保证超过 600。
  3. 逐段校验 finish_reason 而不是只看内容是否为空：若为 length，不加大
     max_tokens（硬约束不能破），而是按更精简的字数要求重问一次；
     若 thinking 参数被端点拒绝（错误码 1210），自动去掉该参数重试。
  4. 拼接后统计汉字数，不足 600 则追加补充小节；仍不足则明确报告卡点并
     以非零码退出，绝不把半截结果当成功交付。

用法：
    export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>
    python3 main.py
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"          # 标准端点上可用 thinking.type=disabled 显式关闭思考
MAX_TOKENS_CAP = 1000      # 网关硬约束：单次请求 max_tokens 绝对上限
SEGMENT_MAX_TOKENS = 850   # 每段实际申请值，给硬约束留安全余量
MIN_HAN = 600              # 正文汉字数下限
TIMEOUT = 120              # 单次 HTTP 超时（秒）
HTTP_RETRY = 3             # 网络/限流层重试次数

REPORT_TITLE = "2026 年中国新能源汽车出口市场简报"

SYSTEM_PROMPT = (
    "你是一名汽车行业首席分析师，为管理层撰写简体中文市场简报。"
    "严格遵守：只输出所指派小节的正文；以指定小标题单独一行开头；"
    "不要任何解释、寒暄、总述或 Markdown 代码块；用连贯段落，不用列表；"
    "数据要具体（数量、金额、同比、占比），口径自洽，可使用行业普遍引用的估计值。"
)

# (小标题, 内容要点, 目标汉字数)。五节目标合计约 950 字，给 600 字底线留足冗余。
SECTIONS = [
    (
        "一、总体规模与增速",
        "2026 年中国新能源汽车出口量（万辆）、出口金额（亿元/美元）、同比增速，"
        "以及新能源汽车占中国汽车整体出口的比重变化",
        200,
    ),
    (
        "二、区域市场格局",
        "欧洲（欧盟关税影响下的恢复情况）、东南亚、拉丁美洲、中东等主要区域市场"
        "的份额与增速对比",
        190,
    ),
    (
        "三、竞争格局与头部车企",
        "比亚迪、奇瑞、上汽名爵、特斯拉上海工厂等头部企业的出口量与市场份额表现",
        190,
    ),
    (
        "四、主要挑战与风险",
        "欧盟反补贴税、滚装船运力瓶颈、海外本地化含量要求、贸易壁垒与汇率波动",
        180,
    ),
    (
        "五、趋势与展望",
        "本地化建厂与产能出海、插电混动出口增长、2027 年市场展望",
        180,
    ),
]

# 正文字数不足 600 时的补充小节（按需取用，同样受 max_tokens<=1000 约束）
EXTRA_SECTIONS = [
    (
        "六、产业链与生态出海",
        "动力电池与零部件随整车出海、海外本地化供应链与售后服务网络建设",
        180,
    ),
    (
        "七、结语",
        "对 2026 年全年出口形势的总体判断与对车企的建议",
        160,
    ),
]


class ApiError(Exception):
    """平台返回的业务层错误（error.code / error.message）。"""

    def __init__(self, code, message):
        super().__init__(f"[{code}] {message}")
        self.code = str(code)
        self.message = str(message)


class SegmentError(Exception):
    """单个小节生成失败，message 里说清卡在哪一步。"""


def count_han(text):
    """统计汉字数（仅 一-鿿，不计标点、数字与英文）。"""
    return len(re.findall(r"[一-鿿]", text))


def clamp_tokens(value):
    """任何情况下发给网关的 max_tokens 都被夹在硬约束之内。"""
    return max(1, min(int(value), MAX_TOKENS_CAP))


def parse_error(resp):
    """从错误响应里提取 (code, message)。"""
    try:
        body = resp.json()
        err = body.get("error") or {}
        return str(err.get("code", resp.status_code)), str(err.get("message", resp.text[:300]))
    except ValueError:
        return str(resp.status_code), resp.text[:300]


def post_with_retry(api_key, payload):
    """网络层/限流重试：仅对超时、连接异常与 429/5xx 重试，其余状态码原样返回。"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last = "未知原因"
    for attempt in range(1, HTTP_RETRY + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last = f"网络异常：{exc}"
            time.sleep(1.5 * attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {resp.status_code}：{resp.text[:200]}"
            time.sleep(1.5 * attempt)
            continue
        return resp
    raise SegmentError(f"连续 {HTTP_RETRY} 次请求失败，最后一次原因：{last}")


def call_model(api_key, messages, max_tokens, disable_thinking):
    """发起一次对话补全。返回 (正文, finish_reason, 回显模型, usage)。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.6,
        "max_tokens": clamp_tokens(max_tokens),
    }
    if disable_thinking:
        # 关键一步：思考 token 计入 max_tokens（速查表 #13），
        # 关闭思考后 850 的预算足以覆盖单节约 200 汉字的正文。
        payload["thinking"] = {"type": "disabled"}
    resp = post_with_retry(api_key, payload)
    if resp.status_code != 200:
        code, msg = parse_error(resp)
        raise ApiError(code, msg)
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise ApiError(err.get("code", "?"), err.get("message", "?"))
    choices = data.get("choices") or []
    if not choices:
        raise ApiError("empty_choices", f"响应中没有 choices：{str(data)[:300]}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content") or ""
    return (
        content.strip(),
        choice.get("finish_reason"),
        data.get("model") or MODEL,
        data.get("usage") or {},
    )


def check_model_echo(echoed):
    """速查表 #2/#3：同步端点不应换模型，但读回 model 字段核对，不一致要处理。"""
    if echoed == MODEL:
        return
    if str(echoed).startswith(MODEL):
        print(f"[提示] 回显模型为 {echoed}（请求 {MODEL}），仅版本后缀差异，继续。",
              file=sys.stderr)
        return
    raise SegmentError(
        f"回显模型 {echoed} 与请求的 {MODEL} 完全不同——计费系数和能力都变了，"
        f"按技能规范报警并停止，请核对模型与端点。"
    )


def clean_segment(text):
    """剥掉模型可能擅自加的 Markdown 代码围栏与多余空行。"""
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def build_messages(title, points, target, concise):
    user = (
        f"撰写《{REPORT_TITLE}》中的一个小节。\n"
        f"小标题：{title}\n"
        f"内容要点：{points}\n"
        f"硬性要求：\n"
        f"1. 以“{title}”单独一行开头，随后接正文段落；\n"
        f"2. 正文约 {target} 个汉字（上下浮动不超过 40 字）；\n"
        f"3. 至少包含 3 个具体数据（数量、金额、同比或占比）；\n"
        f"4. 用连贯的书面段落，不要列表、不要代码块、不要输出本节以外的内容。"
    )
    if concise:
        user += "\n5. 上一次输出因 token 预算被截断，这次请显著精炼表达，优先保住数据。"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def fetch_segment(api_key, title, points, target):
    """生成一个小节。返回 (小节文本, 本次请求实际申请的 max_tokens)。

    失败路径都落在 SegmentError 里，并写明卡在哪一步，方便排查而不是丢半截。
    """
    last_diag = "尚未发起请求"
    for concise in (False, True):
        target_now = max(120, target * 3 // 4) if concise else target
        msgs = build_messages(title, points, target_now, concise)
        try:
            content, finish, echoed, _usage = call_model(
                api_key, msgs, SEGMENT_MAX_TOKENS, disable_thinking=True
            )
        except ApiError as exc:
            if exc.code == "1210":
                # 速查表 #14：不同端点对 thinking 参数的校验不一致，
                # 被拒就去掉该参数重试一次（同步端点 glm-4.6 理论上不会走到这里）。
                try:
                    content, finish, echoed, _usage = call_model(
                        api_key, msgs, SEGMENT_MAX_TOKENS, disable_thinking=False
                    )
                except ApiError as exc2:
                    last_diag = f"API 错误 {exc2.code}：{exc2.message}"
                    continue
            else:
                last_diag = f"API 错误 {exc.code}：{exc.message}"
                continue
        try:
            check_model_echo(echoed)
        except SegmentError as exc:
            raise exc
        if not content:
            last_diag = (
                f"finish_reason={finish}，正文为空"
                f"（速查表 #13：多半是思考 token 吃光了 max_tokens={SEGMENT_MAX_TOKENS} 预算）"
            )
            continue
        if finish == "length":
            # 预算内被截断。硬约束下不能加大 max_tokens，只能压缩字数重问。
            last_diag = (
                f"finish_reason=length（max_tokens={SEGMENT_MAX_TOKENS} 内被截断，"
                f"硬约束不允许调高，需压缩重问）"
            )
            continue
        if finish != "stop":
            last_diag = f"异常 finish_reason={finish}（如 sensitive 为内容安全拦截）"
            continue
        return clean_segment(content), SEGMENT_MAX_TOKENS
    raise SegmentError(f"小节「{title}」生成失败，卡点：{last_diag}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "【失败】环境变量 ZHIPUAI_API_KEY 未设置——卡在鉴权这一步，"
            "尚未发起任何 API 请求，因此没有生成任何正文。\n"
            "请先执行：export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>，"
            "再运行 python3 main.py",
            file=sys.stderr,
        )
        return 2

    sections = list(SECTIONS)
    texts, token_log = [], []

    def run_section(title, points, target):
        text, used = fetch_segment(api_key, title, points, target)
        texts.append(text)
        token_log.append((title, used))

    try:
        for title, points, target in sections:
            run_section(title, points, target)
    except SegmentError as exc:
        print(f"【失败】{exc}", file=sys.stderr)
        print(
            f"已成功 {len(texts)}/{len(sections)} 节，按约定不输出半截结果。"
            "以上卡点信息用于排查。",
            file=sys.stderr,
        )
        return 1

    # 字数兜底：不足 600 汉字就追加补充小节（每次请求仍受 max_tokens<=1000 约束）
    body = "\n\n".join(texts)
    for title, points, target in EXTRA_SECTIONS:
        if count_han(body) >= MIN_HAN:
            break
        try:
            run_section(title, points, target)
        except SegmentError as exc:
            print(f"【警告】补充小节失败：{exc}", file=sys.stderr)
            break
        body = "\n\n".join(texts)

    full_text = REPORT_TITLE + "\n\n" + body
    han = count_han(full_text)
    if han < MIN_HAN:
        print(
            f"【失败】正文汉字数 {han}，未达到 {MIN_HAN} 的要求"
            f"（已用完 {len(SECTIONS) + len(EXTRA_SECTIONS)} 个小节的生成额度）。"
            "按约定不输出半截结果；建议检查网络与模型配额后重试。",
            file=sys.stderr,
        )
        return 1

    print("=" * 48)
    print(full_text)
    print("=" * 48)
    print(f"正文汉字数：{han}（要求不少于 {MIN_HAN}，达标）")
    print(f"共发起 {len(token_log)} 次请求，每次 max_tokens 均为 "
          f"{SEGMENT_MAX_TOKENS}（硬约束上限 {MAX_TOKENS_CAP}，未超出）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
