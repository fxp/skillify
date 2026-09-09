# -*- coding: utf-8 -*-
"""生成《2026 年中国新能源汽车出口》市场简报（不少于 600 汉字，含小标题与数据）。

硬约束（不可协商）：下游网关限制单次请求的 max_tokens 绝对不能超过 1000。

应对策略（依据 bigmodel-cn 接入手册的实测结论，非猜测）：
  * 手册陷阱 #13：思考 token 计入 max_tokens，预算小时会出现
    finish_reason=length、正文为空/截断。因此排除 glm-5.3（官方文档与手册均确认
    其在标准端点强制思考、thinking.type=disabled 会报 1210），改用可显式关闭思考
    的 glm-4.6，并传 thinking={"type":"disabled"}。
  * 手册补救表第③条：预算不能加码时就"分段生成再拼接"。本脚本按小节逐段生成，
    每段目标约 200 汉字（约 300~400 token），远低于 1000 上限，最后拼成完整简报。
  * 每段必须检查 finish_reason：被截断的段落绝不入稿；不能加码 token（硬上限），
    就缩小该段目标字数重试；正文不足 600 汉字时用备选小节补足；最终仍不达标则
    打印完整卡点诊断并以非零码退出，不把半截结果当成功交付。
  * 手册陷阱 #2：同步端点不静默换模型，但仍读回响应的 model 字段核对，
    换成别的模型家族时立即报警停止。

用法：
    ZHIPUAI_API_KEY=<你的Key> python3 main.py

依赖：仅 requests（标准库以外）。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"                # 同步端点不静默换模；支持 thinking.type=disabled

MAX_TOKENS_CAP = 1000            # 网关硬约束：单次请求绝对上限，任何请求不得突破
SEGMENT_MAX_TOKENS = 900         # 每段实际申请额度，留安全余量，绝不会触碰 1000
REQUIRED_HANZI = 600             # 用户要求：完整正文不少于 600 汉字
INTERNAL_TARGET_HANZI = 780      # 内部目标，高于要求以保证余量

NETWORK_RETRY = 3                # 网络异常 / 429 / 5xx 的重试次数
BACKOFF_SECONDS = 2              # 重试退避基数（线性递增）
REQUEST_TIMEOUT = 90

if SEGMENT_MAX_TOKENS > MAX_TOKENS_CAP:
    raise RuntimeError("配置错误：每段 max_tokens 已突破网关上限 %d" % MAX_TOKENS_CAP)

# 生成失败（finish_reason=length 等）时的重试阶梯：缩小目标字数，而不是加码 token
SECTION_TARGET_CHARS = [200, 130, 90]
SECTION_MIN_HANZI = 80           # 一段"合格"的最低汉字数（正常应远高于此）

SECTIONS = [
    ("一、整体规模与增长",
     "2026 年中国新能源汽车出口总量（万辆）、同比增速、纯电与插混的结构占比、"
     "在汽车总出口中的比重"),
    ("二、主要目的地市场",
     "欧洲、东南亚、拉美、中东等区域的份额变化，至少点出 3 个具体国家市场及当地"
     "销量、市占率或增速数据"),
    ("三、竞争格局与头部车企",
     "比亚迪、奇瑞、上汽、吉利等头部玩家的出口量与市占率，新势力与国企出海的最新进展"),
    ("四、挑战与风险",
     "欧盟反补贴关税、美国等地贸易壁垒、滚装船运力与海运成本、数据与本地化合规要求"),
]
RESERVE_SECTIONS = [             # 正文不足 600 汉字时按序追加的备选小节
    ("五、供应链与本地化布局",
     "动力电池与零部件随整车出海，匈牙利、泰国、巴西等海外工厂的产能投放节奏"),
    ("六、全年展望",
     "2026 全年出口量预期区间、增长动能切换逻辑、对 2027 年的简要展望"),
]

SYSTEM_PROMPT = (
    "你是资深的汽车行业市场分析师，为管理层撰写中文市场简报。严格遵守："
    "只输出所要求的小节本身；不要开场白、不要客套、不要总结语；"
    "不要使用代码块或 Markdown 围栏；小节以规定的标题行开头；"
    "正文必须包含具体的数字（数量、金额、百分比、排名等），"
    "数据基于你训练语料中的公开行业数据与趋势给出合理估计。"
)

REQUEST_LOG = []                 # 记录每一笔请求，结束时打印，证明从未突破 max_tokens 上限
USE_THINKING_DISABLED = True     # 若平台参数校验拒绝该参数（报 1210），自动去掉重试


def count_hanzi(text):
    """统计汉字数（Unicode 基本区），不含标点、数字、字母与空白。"""
    return len(re.findall(r"[一-鿿]", text))


def strip_code_fences(text):
    """防御性剥掉模型可能包上的 ``` 围栏（手册陷阱 #16 的近似场景）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def call_chat(messages, purpose):
    """发起一次对话补全，返回 (content, finish_reason, usage)。

    max_tokens 恒为 SEGMENT_MAX_TOKENS（≤ 网关硬上限 1000），在函数内再次钳制并
    校验——这是对硬约束的双重保险。
    """
    max_tokens = min(SEGMENT_MAX_TOKENS, MAX_TOKENS_CAP)
    if max_tokens > MAX_TOKENS_CAP:
        raise RuntimeError("内部错误：max_tokens=%d 将突破网关上限" % max_tokens)

    global USE_THINKING_DISABLED
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(1, NETWORK_RETRY + 1):
        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.6,
        }
        if USE_THINKING_DISABLED:
            # 陷阱 #13/#14：思考 token 计入 max_tokens，必须显式关闭；
            # glm-4.6 官方支持显式开关。若参数被拒则去掉重试（见下）。
            payload["thinking"] = {"type": "disabled"}

        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = "网络异常: %s" % exc
            time.sleep(BACKOFF_SECONDS * attempt)
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = "HTTP %d（第 %d 次尝试）" % (resp.status_code, attempt)
            time.sleep(BACKOFF_SECONDS * attempt)
            continue

        try:
            body = resp.json()
        except ValueError:
            last_error = "HTTP %d，响应不是 JSON: %s" % (
                resp.status_code, resp.text[:200])
            break  # 非可重试错误

        if resp.status_code != 200 or body.get("error"):
            err = body.get("error") or {}
            code = err.get("code")
            message = err.get("message", resp.text[:200])
            if str(code) == "1210" and "thinking" in str(message):
                # 端点参数校验不一致（陷阱 #14）：去掉 thinking 参数降级重试
                USE_THINKING_DISABLED = False
                last_error = "参数 thinking 被拒绝（%s: %s），去掉后重试" % (
                    code, message)
                continue
            last_error = "业务错误 HTTP %d code=%s message=%s" % (
                resp.status_code, code, message)
            break  # 参数/鉴权/余额类错误，换姿势重试无意义

        choices = body.get("choices") or []
        if not choices:
            last_error = "响应缺少 choices: %s" % str(body)[:200]
            time.sleep(BACKOFF_SECONDS * attempt)
            continue

        choice = choices[0]
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason")
        usage = body.get("usage") or {}

        # 陷阱 #2/#3：读回回显 model 核对。版本号后缀差异可容忍，换家族必须停下。
        model_echo = body.get("model") or ""
        if model_echo and not model_echo.lower().startswith(MODEL):
            REQUEST_LOG.append({"purpose": purpose, "max_tokens": max_tokens,
                                "error": "回显模型 %s 与请求的 %s 不一致"
                                         % (model_echo, MODEL)})
            raise RuntimeError(
                "回显模型 %s 与请求的 %s 不一致，计费系数与能力可能已变，停止执行"
                % (model_echo, MODEL))

        completion_details = usage.get("completion_tokens_details") or {}
        REQUEST_LOG.append({
            "purpose": purpose,
            "attempt": attempt,
            "max_tokens": max_tokens,
            "model_echo": model_echo,
            "finish_reason": finish_reason,
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": completion_details.get("reasoning_tokens"),
            "hanzi": count_hanzi(content),
        })
        return content, finish_reason, usage

    REQUEST_LOG.append({"purpose": purpose, "max_tokens": max_tokens,
                        "error": last_error or "未知错误"})
    return None, None, None


def build_section_prompt(title, requirement, target_chars):
    return (
        "撰写市场简报《2026 年中国新能源汽车出口》中的一个小节。\n"
        "标题行（原样使用）：## %s\n"
        "内容要点：%s。\n"
        "硬性要求：标题行之后紧跟一段完整正文，约 %d 字，至少包含 3 个具体数字；"
        "只写这一个段落，写完即止；不要分点罗列，不要输出其他小节，"
        "不要任何开场白和结尾说明。" % (title, requirement, target_chars)
    )


def write_section(title, requirement):
    """生成一个小节。返回 (小节文本或 None, 诊断信息列表)。"""
    diagnostics = []
    for attempt, target_chars in enumerate(SECTION_TARGET_CHARS, 1):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_section_prompt(
                title, requirement, target_chars)},
        ]
        content, finish_reason, _usage = call_chat(messages, title)
        if content is None:
            diagnostics.append("第 %d 次请求失败（call_chat 内已重试网络/5xx，"
                               "详见请求日志）" % attempt)
            break  # 传输层/业务错误换目标字数也救不了，直接定性失败

        text = strip_code_fences(content)
        hanzi = count_hanzi(text)
        if finish_reason == "stop" and hanzi >= SECTION_MIN_HANZI:
            return text, diagnostics
        if finish_reason == "stop":
            diagnostics.append("第 %d 次 finish_reason=stop 但仅 %d 汉字"
                               "（低于 %d），疑似模型没写够" % (
                                   attempt, hanzi, SECTION_MIN_HANZI))
        else:
            # finish_reason=length：正文被 max_tokens 截断（陷阱 #13）。
            # 硬上限 1000 不能加码，只能缩小该段目标字数重试；
            # sensitive / network_error 同样走缩小重试，最多用完阶梯。
            diagnostics.append("第 %d 次 finish_reason=%s，得到 %d 汉字"
                               "（目标 %d），该段不采用" % (
                                   attempt, finish_reason, hanzi, target_chars))
    return None, diagnostics


def print_request_log():
    print("\n请求明细（验证 max_tokens 硬约束，每次均 ≤ %d）：" % MAX_TOKENS_CAP)
    for i, item in enumerate(REQUEST_LOG, 1):
        if "error" in item:
            print("  #%d [%s] 失败：%s" % (i, item["purpose"], item["error"]))
            continue
        reasoning = item.get("reasoning_tokens")
        reasoning_str = (", reasoning_tokens=%s" % reasoning
                         if reasoning is not None else "")
        print("  #%d [%s] max_tokens=%d, 回显model=%s, finish_reason=%s, "
              "completion_tokens=%s%s, 正文汉字=%d" % (
                  i, item["purpose"], item["max_tokens"], item["model_echo"],
                  item["finish_reason"], item["completion_tokens"],
                  reasoning_str, item["hanzi"]))


def main():
    if not os.environ.get("ZHIPUAI_API_KEY"):
        print("【失败】环境变量 ZHIPUAI_API_KEY 未设置，一次 API 请求都发不出去。",
              file=sys.stderr)
        print("卡点：拿不到鉴权凭证。请先执行：export ZHIPUAI_API_KEY=<你的Key>，"
              "再运行 python3 main.py", file=sys.stderr)
        return 1

    parts = []
    failures = []

    def assembled_hanzi():
        return count_hanzi("\n\n".join(parts))

    try:
        # 第一轮：主干小节；凑够内部目标就提前停，少花请求
        for title, requirement in SECTIONS:
            text, diag = write_section(title, requirement)
            if diag:
                failures.append((title, diag))
            if text:
                parts.append(text)
                if assembled_hanzi() >= INTERNAL_TARGET_HANZI:
                    break

        # 第二轮：主干没凑够（有小节失败或字数不足）时，用备选小节补足
        reserve = list(RESERVE_SECTIONS)
        while assembled_hanzi() < REQUIRED_HANZI and reserve:
            title, requirement = reserve.pop(0)
            text, diag = write_section(title, requirement)
            if diag:
                failures.append((title, diag))
            if text:
                parts.append(text)

        body = "\n\n".join(parts)
        hanzi = count_hanzi(body)

        if hanzi < REQUIRED_HANZI:
            # 任务要求：拿不到就说明白卡在哪，不输出半截结果
            print("\n【失败】正文仅 %d 汉字（要求 ≥ %d），不输出半截结果。"
                  "卡点诊断：" % (hanzi, REQUIRED_HANZI), file=sys.stderr)
            for title, diag in failures:
                print("  - 小节[%s]：%s" % (title, "；".join(diag)),
                      file=sys.stderr)
            print("  备选小节已用尽，还差 %d 汉字。" % (REQUIRED_HANZI - hanzi),
                  file=sys.stderr)
            print("  最可能原因：单次请求 max_tokens 硬上限 %d 导致长段被截断"
                  "（finish_reason=length），或 API 侧报错（见下方请求日志）。"
                  % MAX_TOKENS_CAP, file=sys.stderr)
            print_request_log()
            return 1

        title_line = "# 2026 年中国新能源汽车出口市场简报"
        date_line = "（生成日期：%s，基于 GLM 行业趋势估计）" % (
            time.strftime("%Y-%m-%d"),)
        note_line = ("注：文中数据由 GLM 模型基于公开行业趋势估算生成，"
                     "正式引用请以海关总署、中汽协等官方统计为准。")
        full = "%s\n\n%s\n\n%s\n\n%s" % (title_line, date_line, body, note_line)

        print("=" * 72)
        print(full)
        print("=" * 72)
        non_space = len(re.sub(r"\s", "", full))
        print("\n【统计】正文汉字数：%d（要求 ≥ %d，达标，余量 %d）"
              % (hanzi, REQUIRED_HANZI, hanzi - REQUIRED_HANZI))
        print("【统计】简报总字符数（不含空白）：%d" % non_space)
        print("【统计】共 %d 次请求，单次 max_tokens=%d，网关上限 %d，全程未突破。"
              % (len(REQUEST_LOG), SEGMENT_MAX_TOKENS, MAX_TOKENS_CAP))
        if failures:
            print("【提示】以下小节曾重试过（已自动补救成功）：%s"
                  % "、".join(t for t, _ in failures))
        print_request_log()
        return 0

    except RuntimeError as exc:
        print("\n【失败】%s" % exc, file=sys.stderr)
        print_request_log()
        return 1


if __name__ == "__main__":
    sys.exit(main())
