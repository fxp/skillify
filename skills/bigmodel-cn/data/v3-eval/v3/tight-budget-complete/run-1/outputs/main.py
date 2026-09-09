#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口市场简报》。

硬约束：下游网关限制「单次请求 max_tokens 绝对不能超过 1000」。
本脚本所有请求统一走 MAX_TOKENS_PER_REQUEST = 1000，请求函数内有
运行期断言兜底，任何路径都不可能发出超限请求。

在 1000 token 预算内拿到 600+ 汉字完整正文的策略（对应技能手册的补救阶梯）：
  1) 关闭深度思考：思考 token 计入 max_tokens，600 字简报的思考链实测
     就要 2400+ token，不关思考这个预算根本不够。glm-5.3 / glm-4.7 在
     标准端点强制思考（关不掉），所以选 thinking.type=disabled 可生效的
     glm-5.2（备选 glm-4.6 / glm-4.5）；
  2) 分段生成再拼接：整篇关思考也要 ~1500 token，单请求装不下；拆成
     每节 200 字上下的小节，单节远小于 1000 token；
  3) 每次响应检查 finish_reason：命中 "length"（被截断）不报错退出，
     而是换更短的篇幅目标重写该节——max_tokens 不能加大，只能往小调；
  4) 拼接后实数汉字，不足 600 就追加补充小节；最终仍不达标则明确报
     失败并说清卡点，绝不把半截内容当成品交出去。

API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖 requests。
用法：python3 main.py
"""

import os
import re
import sys
import time

import requests

API_KEY_ENV = "ZHIPUAI_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 网关硬上限：单次请求 max_tokens 绝不能超过 1000。
MAX_TOKENS_PER_REQUEST = 1000

# 模型候选：必须是标准端点上 thinking.type=disabled 能生效的模型。
# glm-5.3 / glm-5.3-flash / glm-4.7 / glm-4.5v 强制思考，思考 token 会
# 挤占 max_tokens 预算，直接排除。按能力从高到低探测，第一个可用的胜出。
MODEL_CANDIDATES = ["glm-5.2", "glm-4.6", "glm-4.5"]

REQUEST_TIMEOUT = 60   # 单次请求超时（秒）
NETWORK_RETRIES = 3    # 网络 / 5xx / 429 的重试次数
TARGET_HANZI = 600     # 正文汉字数硬指标

BRIEF_TITLE = "2026年中国新能源汽车出口市场简报"

SYSTEM_PROMPT = (
    "你是一名汽车行业资深市场分析师，为客户端撰写严谨的中文市场简报。"
    "行文要求：书面语，信息密度高，数据具体（数量、增速、占比、金额），不堆砌形容词。"
)

# 主小节规划：5 节 × 约 200 汉字，目标 1000 汉字上下，给 600 的硬指标留足冗余。
SECTION_SPECS = [
    ("一、总体规模与增长态势",
     "2026 年中国新能源汽车出口总量（预估口径）、同比增速、新能源汽车占汽车整体出口的比重"),
    ("二、区域市场与目的地结构",
     "欧洲、东南亚、拉美、中东、中亚等主要出口目的地的份额与变化，纯电与插混的车型结构"),
    ("三、竞争格局与头部企业",
     "比亚迪、奇瑞、上汽、长城等头部自主车企的出口量级与市场份额，明星车型表现"),
    ("四、价格、成本与盈利",
     "出口平均单价变化、海运运力与运费、关税成本压力对出口盈利的影响"),
    ("五、风险因素与全年展望",
     "欧盟反补贴税与本地化建厂、贸易壁垒与技术法规、2026 全年出口形势判断"),
]

# 补充小节：主小节拼完后汉字数仍不足 600 时按序启用。
SUPPLEMENT_SPECS = [
    ("六、延伸观察：补能与服务体系出海",
     "充电桩、换电与售后服务网络随整车出海的进展与数据"),
    ("七、延伸观察：二手车出口与运力",
     "新能源汽车二手车出口规模、滚装船运力投放情况"),
    ("八、延伸观察：供应链与电池出海",
     "动力电池及零部件企业伴随整车出海的产能布局"),
]

# 截断补救阶梯：(下限字数, 上限字数, 可接受的最低汉字数)。
# 命中 max_tokens 截断时逐级压缩篇幅重写——预算不能加，只能往小调。
LENGTH_LADDER = [(180, 260, 120), (120, 180, 80), (70, 120, 50)]

# 每次真实发出的 API 请求的审计记录，结束时打印以自证未超限。
REQUEST_AUDIT = []

HANZI_RE = re.compile(r"[一-鿿]")


class ApiError(Exception):
    """平台返回的业务错误（带 error 字段或明确的 HTTP 错误）。"""

    def __init__(self, status, code, message):
        super().__init__(f"HTTP {status}，错误码 {code}：{message}")
        self.status = status
        self.code = str(code)


class SectionError(Exception):
    """某一小节多轮重写后仍拿不到完整正文。"""


def count_hanzi(text):
    """统计汉字数（只数中日韩统一表意文字，不含标点、数字、字母）。"""
    return len(HANZI_RE.findall(text))


def fail(message, exit_code):
    """明确报告卡点后退出，不把半截内容当成品输出。"""
    print(f"[失败] {message}", file=sys.stderr)
    sys.exit(exit_code)


def api_error_hint(text):
    """对常见错误码补充排查提示（1113 不一定是余额问题，别让用户瞎充值）。"""
    if "1113" in text:
        return ("提示：1113 有三种成因——端点不对 / 能力不在套餐 / 模型不在套餐。"
                "若你用的是 GLM Coding Plan 套餐 Key，它不能打标准端点 …/api/paas/v4，"
                "需要改用 …/api/coding/paas/v4 并配套餐 Key。")
    return ""


def call_chat(api_key, model, messages, max_tokens=MAX_TOKENS_PER_REQUEST):
    """发一次对话补全请求。max_tokens 超过硬上限时直接断言失败，绝不发出。"""
    if max_tokens > MAX_TOKENS_PER_REQUEST:
        raise AssertionError(
            f"max_tokens={max_tokens} 超过网关硬上限 {MAX_TOKENS_PER_REQUEST}，拒绝发送"
        )
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # 思考 token 计入 max_tokens，预算紧张必须关掉（glm-5.2/4.6/4.5 支持显式关闭）。
        "thinking": {"type": "disabled"},
        "temperature": 0.6,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error = None
    for attempt in range(NETWORK_RETRIES):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            resp = requests.post(CHAT_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"网络异常：{exc}"
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}：{resp.text[:200]}"
            continue
        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(f"响应不是合法 JSON：{resp.text[:200]}")
        if isinstance(body, dict) and body.get("error"):
            error = body["error"]
            raise ApiError(resp.status_code, error.get("code"), error.get("message"))
        resp.raise_for_status()
        # 静默换模型检测：回显与请求不一致只报警不中断（计费系数可能变化，需人工核对）。
        echoed = body.get("model") or ""
        if echoed and not echoed.lower().startswith(model.lower()):
            print(f"[警告] 请求模型 {model}，响应回显 {echoed}，请核对计费模型",
                  file=sys.stderr)
        usage = body.get("usage") or {}
        choices = body.get("choices") or [{}]
        REQUEST_AUDIT.append({
            "model": echoed or model,
            "max_tokens": max_tokens,
            "finish_reason": choices[0].get("finish_reason"),
            "completion_tokens": usage.get("completion_tokens"),
        })
        return body
    raise RuntimeError(f"重试 {NETWORK_RETRIES} 次仍失败，最后错误：{last_error}")


def extract_choice(body):
    """取出 (正文, finish_reason)。判完成度看 finish_reason，不看空串。"""
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应缺少 choices：{str(body)[:200]}")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    return content, choices[0].get("finish_reason")


def choose_model(api_key):
    """用最小请求探测候选模型，返回第一个可用的。

    平台模型迭代快，文档可用的模型可能已下架或参数校验变化，
    探测失败就降级到下一个候选，而不是整个任务失败。
    """
    reasons = []
    probe = [{"role": "user", "content": "连通性探测：请只回复两个字：可用"}]
    for model in MODEL_CANDIDATES:
        try:
            body = call_chat(api_key, model, probe, max_tokens=32)
            content, finish = extract_choice(body)
        except (ApiError, RuntimeError) as exc:
            reasons.append(f"{model}：{exc}")
            continue
        if not content or finish not in ("stop", "length"):
            reasons.append(f"{model}：探测响应异常 finish_reason={finish}")
            continue
        return model
    raise RuntimeError("；".join(reasons))


def generate_section(api_key, model, title, brief):
    """生成一个小节。被截断就压篇幅重写，拿到完整正文才返回。"""
    finish = None
    for round_no, (lo, hi, floor) in enumerate(LENGTH_LADDER):
        notes = ""
        if round_no:
            notes = "上一次输出被 max_tokens 截断，这次务必写得更紧凑。"
        user = (
            f"撰写市场简报中的一个小节。\n"
            f"小标题：{title}\n"
            f"内容要点：{brief}\n"
            f"硬性要求：\n"
            f"1) 正文 {lo}~{hi} 个汉字；\n"
            f"2) 至少包含 3 个具体数据（数量、增速、占比或金额，可给行业预估口径）；\n"
            f"3) 不要输出小标题、开场白、结尾总结，不要分点列表，直接写连贯的正文段落；\n"
            f"4) 在 {hi} 字以内自然收尾，确保语义完整。{notes}"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        body = call_chat(api_key, model, messages)
        content, finish = extract_choice(body)
        if finish == "length":
            # 预算内被截断：max_tokens 不能加（硬约束），换更短的目标重写。
            print(f"[小节] {title} 第 {round_no + 1} 稿命中 max_tokens 截断，压缩篇幅重写",
                  file=sys.stderr)
            continue
        if finish != "stop":
            raise SectionError(f"小节「{title}」异常结束：finish_reason={finish}")
        if count_hanzi(content) >= floor:
            return content
        # finish_reason=stop 但字数不足：原地按同一目标重写一次。
        short_by = count_hanzi(content)
        print(f"[小节] {title} 第 {round_no + 1} 稿仅 {short_by} 汉字（要求约 {lo}），重写",
              file=sys.stderr)
        messages[1]["content"] += f"\n你上次只写了 {short_by} 个汉字，请务必写满 {lo}~{hi} 个汉字。"
        body = call_chat(api_key, model, messages)
        content, finish = extract_choice(body)
        if finish == "stop" and count_hanzi(content) >= floor:
            return content
        if finish == "length":
            continue
        if finish != "stop":
            raise SectionError(f"小节「{title}」异常结束：finish_reason={finish}")
    raise SectionError(
        f"小节「{title}」重写 {len(LENGTH_LADDER)} 轮仍拿不到完整正文"
        f"（最后 finish_reason={finish}），卡在 max_tokens={MAX_TOKENS_PER_REQUEST} 的预算内"
    )


def render_briefing(sections):
    lines = [BRIEF_TITLE, ""]
    for heading, body_text in sections:
        lines.append(heading)
        lines.append(body_text)
        lines.append("")
    return "\n".join(lines).strip()


def main():
    print(f"开始生成《{BRIEF_TITLE}》"
          f"（单次请求 max_tokens 硬上限 {MAX_TOKENS_PER_REQUEST}）", file=sys.stderr)

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        fail(f"环境变量 {API_KEY_ENV} 未设置或为空：没有 API Key 就无法调用"
             f"智谱开放平台。请先执行 export {API_KEY_ENV}=<你的Key> 再运行。", 2)

    try:
        model = choose_model(api_key)
    except RuntimeError as exc:
        fail(f"卡在模型探测阶段，所有候选（{'、'.join(MODEL_CANDIDATES)}）都不可用：{exc}"
             f"{api_error_hint(str(exc))}", 3)
    print(f"[模型] 使用 {model}（thinking 已关闭，思考 token 不占 max_tokens 预算）",
          file=sys.stderr)

    sections = []
    try:
        for heading, brief in SECTION_SPECS:
            print(f"[进度] 撰写小节：{heading}", file=sys.stderr)
            sections.append((heading, generate_section(api_key, model, heading, brief)))
        for heading, brief in SUPPLEMENT_SPECS:
            if count_hanzi(render_briefing(sections)) >= TARGET_HANZI:
                break
            print(f"[进度] 正文汉字数不足 {TARGET_HANZI}，补写小节：{heading}", file=sys.stderr)
            sections.append((heading, generate_section(api_key, model, heading, brief)))
    except ApiError as exc:
        fail(f"调用 API 失败，已中止且不输出半成品：{exc}{api_error_hint(str(exc))}", 5)
    except SectionError as exc:
        fail(f"{exc}。按约定不把不完整的正文交出去，已中止。", 4)

    briefing = render_briefing(sections)
    hanzi = count_hanzi(briefing)
    if hanzi < TARGET_HANZI:
        fail(f"全部小节生成完毕，但正文只有 {hanzi} 汉字，未达到 {TARGET_HANZI} 汉字的要求，"
             f"不作为成品输出。卡点：模型在单请求 {MAX_TOKENS_PER_REQUEST} token 预算内"
             f"未能产出足量正文。", 6)

    print("=" * 48)
    print(briefing)
    print("=" * 48)
    print(f"正文汉字数：{hanzi} 字（要求不少于 {TARGET_HANZI} 字，达标）")
    print(f"正文总字符数（含标题、标点、数字）：{len(briefing)}")
    used_max = max((row["max_tokens"] for row in REQUEST_AUDIT), default=0)
    print(f"共发起 API 请求 {len(REQUEST_AUDIT)} 次，单次 max_tokens 最大值 {used_max}"
          f"（网关硬上限 {MAX_TOKENS_PER_REQUEST}，未超限）")
    print("请求审计：")
    for row in REQUEST_AUDIT:
        print(f"  - model={row['model']}  max_tokens={row['max_tokens']}  "
              f"finish_reason={row['finish_reason']}  "
              f"completion_tokens={row['completion_tokens']}")


if __name__ == "__main__":
    main()
