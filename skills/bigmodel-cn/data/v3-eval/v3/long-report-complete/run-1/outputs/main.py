#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报（≥600 字、含小标题与具体数据）。

设计要点（对应 bigmodel-cn 技能包的实测踩坑记录）：
- 标准 API：POST https://open.bigmodel.cn/api/paas/v4/chat/completions，Bearer 鉴权，
  Key 只从环境变量 ZHIPUAI_API_KEY 读取，不硬编码。
- 陷阱 #13：思考 token 计入 max_tokens，预算不足会 finish_reason=length、正文截断甚至为空
  → 首轮就给 max_tokens=8192（技能实测 600 字简报思考链要 2400+，3000 才够），并用
    reasoning_effort=low 压缩思考链；命中 length 就按补救表翻倍预算重试。
- 陷阱 #14：glm-5.3 在标准端点思考强制开启，传 thinking:disabled 会报 1210
  → 降级路径换 glm-5.2（标准端点允许显式关思考）重试；仍不行则分段生成再拼接。
- 陷阱 #2/#3：读回响应里的 model 字段核对服务端回显，防止被静默换成别的模型。
- 只依赖 requests + 标准库。拿到「完整且达标」的结果才打印交付，绝不输出半截内容：
  三级策略依次是 ① glm-5.3 整篇生成（预算翻倍重试）→ ② glm-5.2 关思考重试
  → ③ 分小节生成后拼接；全部失败才报错退出。
"""

import json
import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
PRIMARY_MODEL = "glm-5.3"   # 旗舰；标准端点思考强制开启（陷阱 #14），思考计入 max_tokens（#13）
FALLBACK_MODEL = "glm-5.2"  # 标准端点允许 thinking.type=disabled，可绕开思考吃预算
MIN_CHARS = 600             # 硬性字数下限
TARGET_CHARS = 900          # 提示词里要求的字数，给校验留余量
TIMEOUT = (10, 300)         # 思考模型出稿较慢，读超时给足

SYSTEM_PROMPT = "你是一名资深汽车行业分析师，擅长为管理层撰写数据翔实、观点明确的市场简报。"

USER_PROMPT = f"""请撰写一份主题为「2026 年中国新能源汽车出口」的中文市场简报，要求：
1. 全文不少于{TARGET_CHARS}字；
2. 第一行为总标题（以 # 开头），正文用 Markdown 二级小标题（以 ## 开头）分成至少 4 个部分，
   建议涵盖：总体规模与增速、主要目标市场、竞争格局与头部企业、挑战与风险、趋势展望；
3. 每个部分都必须给出具体数据（出口量、同比增速、金额、市场份额等，要有数字），
   可基于你掌握的行业知识给出合理估计；
4. 最后一部分是结论与展望，必须以完整句子收尾，不得中途停笔；
5. 直接输出简报正文，不要任何解释性开场白或结尾说明。"""

# 策略③分段生成用的小节提纲：(小标题, 内容要点)
SECTIONS = [
    ("总体规模与增速", "2026 年以来中国新能源汽车出口量（万辆）、同比增速、出口金额与平均单价变化"),
    ("主要目标市场", "欧洲、东南亚、拉美、中东等重点区域的占比与变化，点名具体国家或地区的数据"),
    ("竞争格局与头部企业", "比亚迪、奇瑞、上汽等头部企业的出口量与份额，纯电/插混产品结构变化"),
    ("挑战与风险", "欧盟反补贴关税、贸易壁垒、海运运力、海外本地化合规等压力"),
    ("趋势展望与结论", "2026 全年出口量预测、本地化建厂与出口结构升级方向，给出判断并完整收尾"),
]


def log(msg):
    """进度与诊断信息走 stderr，stdout 只留简报与校验结论。"""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- HTTP 层 --

def _post_with_retry(payload, api_key, attempts=3):
    """发起一次 chat/completions 调用，对瞬时故障（网络异常/429/5xx）做指数退避重试。

    4xx 业务错误（如 1113 余额不足、1210 参数非法）重试没有意义，直接抛 RuntimeError，
    由上层策略决定是否换路径。
    """
    last_err = None
    for i in range(attempts):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            last_err = exc
            wait = 2 ** i
            log(f"[重试] 网络异常：{exc}，{wait}s 后重试")
            time.sleep(wait)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and i < attempts - 1:
            wait = 2 ** i
            log(f"[重试] HTTP {resp.status_code}，{wait}s 后重试")
            time.sleep(wait)
            continue
        break
    else:
        raise RuntimeError(f"网络重试 {attempts} 次仍失败：{last_err}")

    if resp.status_code >= 400:
        code, message = "?", resp.text[:300]
        try:
            err = resp.json().get("error") or {}
            code = err.get("code", "?")
            message = err.get("message", message)
        except ValueError:
            pass
        raise RuntimeError(f"API 错误 HTTP {resp.status_code} code={code}：{message}")
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"响应不是合法 JSON：{resp.text[:200]}")


def _extract(data):
    """从响应里取出 (正文, finish_reason, 回显模型名)。"""
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应缺少 choices：{json.dumps(data, ensure_ascii=False)[:300]}")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return content, choices[0].get("finish_reason"), data.get("model", "")


def _check_model_echo(requested, echoed):
    """陷阱 #2/#3：核对服务端回显的模型，防止被静默重路由。

    同族版本号差异（如 glm-5.3 -> glm-5.3-xxx）记日志继续；换成完全不同的模型则报警停下。
    """
    if not echoed or echoed == requested:
        return
    if echoed.startswith(requested) or requested.startswith(echoed):
        log(f"[警告] 服务端回显模型为 {echoed}（请求 {requested}），属同族版本差异，继续。")
        return
    raise RuntimeError(
        f"服务端实际使用的模型是 {echoed}，与请求的 {requested} 完全不同（计费系数与能力都变了），停止本策略。"
    )


# ---------------------------------------------------------------- 校验层 --

def count_chars(text):
    """中文字数口径：去掉空白与 Markdown 标记符号后统计字符数（宁少勿多，偏保守）。"""
    return len(re.sub(r"[\s#*>`|-]", "", text))


def find_subheadings(text):
    """收集二级及以下 Markdown 小标题，或「一、」式中文序号标题行。"""
    titles = re.findall(r"^\s*#{2,4}\s+(.+?)\s*$", text, re.MULTILINE)
    titles += re.findall(r"^\s*([一二三四五六七八九十]+、\s*\S+.*)$", text, re.MULTILINE)
    return [t.strip() for t in titles]


def ends_complete(text):
    return text.rstrip().endswith(("。", "！", "？", "”", "’", "）", "】", "」"))


def validate(text, finish_reason):
    """完整性 + 达标校验。返回 (是否通过, 问题列表, 统计信息)。"""
    problems = []
    stats = {
        "chars": count_chars(text),
        "subheadings": find_subheadings(text),
        "data_points": len(re.findall(r"\d+(?:\.\d+)?", text)),
        "finish_reason": finish_reason or "(空)",
    }
    if not text.strip():
        problems.append("正文为空")
    if finish_reason != "stop":
        problems.append(f"finish_reason={stats['finish_reason']}，未正常收尾（length=被 max_tokens 截断）")
    if stats["chars"] < MIN_CHARS:
        problems.append(f"字数不足（{stats['chars']} < {MIN_CHARS}）")
    if len(stats["subheadings"]) < 3:
        problems.append(f"小标题不足（{len(stats['subheadings'])} < 3）")
    if stats["data_points"] < 5:
        problems.append("具体数据不足（数字出现少于 5 处）")
    if text.strip() and not ends_complete(text):
        problems.append("结尾不是完整句子，疑似半截内容")
    return (not problems), problems, stats


# ---------------------------------------------------------------- 生成策略 --

def _base_payload(model, user_content, max_tokens):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }


def _run_until_valid(build_payload, model, max_attempts, label):
    """通用循环：调 API → 核对回显 → 校验；命中截断/空正文则翻倍预算带上反馈重试。"""
    max_tokens = 8192 if model == PRIMARY_MODEL else 4096
    extra_note = ""
    for attempt in range(1, max_attempts + 1):
        payload = build_payload(max_tokens, extra_note)
        log(f"[{label}] 第 {attempt}/{max_attempts} 次尝试：model={model} max_tokens={max_tokens}")
        data = _post_with_retry(payload, os.environ["ZHIPUAI_API_KEY"])
        content, finish_reason, echoed = _extract(data)
        _check_model_echo(model, echoed)
        ok, problems, stats = validate(content, finish_reason)
        if ok:
            return content
        log(f"[{label}] 未达标：{'；'.join(problems)}")
        if finish_reason == "length" or not content.strip():
            # 补救①（陷阱 #13）：思考计入 max_tokens，预算不够就翻倍重试
            max_tokens *= 2
            extra_note = "注意：上一次输出因 token 预算不足被截断，请从头完整重写全文，务必写到结论最后一句。"
        elif finish_reason == "network_error":
            extra_note = ""  # 瞬时推理异常，原预算直接重试
        else:
            extra_note = f"注意：上一次输出不达标（{'；'.join(problems)}），请重新完整输出。"
    return None


def strategy_whole(api_key):
    """策略①：glm-5.3 整篇生成。标准端点思考强制开启，不传 thinking（传 disabled 会 1210）。"""
    try:
        return _run_until_valid(
            lambda max_tokens, note: {
                **_base_payload(PRIMARY_MODEL, USER_PROMPT + note, max_tokens),
                # glm-5.3 只能用 reasoning_effort 控制思考强度：low 显著缩短思考链，
                # 省下的预算留给正文（valid: low/high/max）
                "reasoning_effort": "low",
            },
            PRIMARY_MODEL,
            max_attempts=3,
            label="策略1-glm5.3整篇",
        )
    except RuntimeError as exc:
        log(f"[策略1-glm5.3整篇] 失败：{exc}")
        return None


def strategy_no_thinking(api_key):
    """策略②：换 glm-5.2 并显式关闭思考（补救②；glm-5.3 在标准端点不支持这么做）。"""
    try:
        return _run_until_valid(
            lambda max_tokens, note: {
                **_base_payload(FALLBACK_MODEL, USER_PROMPT + note, max_tokens),
                "thinking": {"type": "disabled"},
            },
            FALLBACK_MODEL,
            max_attempts=2,
            label="策略2-glm5.2关思考",
        )
    except RuntimeError as exc:
        log(f"[策略2-glm5.2关思考] 失败：{exc}")
        return None


def strategy_segmented(api_key):
    """策略③：分段生成再拼接（补救③）。每个小节独立调用、独立校验，单节截断就地翻倍重试一次。"""

    def one_section(title, points):
        prompt = (
            f"请为市场简报《2026 年中国新能源汽车出口》撰写小节「{title}」。"
            f"内容要点：{points}。要求：正文 150~220 字；至少引用两个具体数字；"
            f"第一行输出「## {title}」，随后写正文；以完整句子结尾；不要输出除此以外的任何内容。"
        )
        max_tokens = 2048
        for attempt in (1, 2):
            payload = {
                **_base_payload(FALLBACK_MODEL, prompt, max_tokens),
                "thinking": {"type": "disabled"},
            }
            log(f"[策略3-分段] 小节「{title}」第 {attempt} 次尝试 max_tokens={max_tokens}")
            data = _post_with_retry(payload, api_key)
            content, finish_reason, echoed = _extract(data)
            _check_model_echo(FALLBACK_MODEL, echoed)
            if content.strip() and finish_reason == "stop" and ends_complete(content):
                return content.strip()
            log(f"[策略3-分段] 「{title}」不完整（finish_reason={finish_reason}），翻倍预算重试")
            max_tokens *= 2
        return None

    parts = ["# 2026 年中国新能源汽车出口市场简报"]
    for title, points in SECTIONS:
        section = one_section(title, points)
        if section is None:
            log(f"[策略3-分段] 小节「{title}」两次尝试均未得到完整内容，放弃本策略")
            return None
        parts.append(section)
    full = "\n\n".join(parts) + "\n"
    ok, problems, _ = validate(full, "stop")
    if not ok:
        log(f"[策略3-分段] 拼接后整体校验未通过：{'；'.join(problems)}")
        return None
    return full


# ---------------------------------------------------------------- 主流程 --

def deliver(text, stats):
    """打印简报全文与明确的达标结论。"""
    line = "=" * 46
    print(line)
    print(text)
    print(line)
    subs = stats["subheadings"]
    print("—— 校验结果 ——")
    print(f"字数：{stats['chars']} 字（口径：去除空白与 Markdown 标记），要求 ≥{MIN_CHARS} 字 → "
          f"{'达标' if stats['chars'] >= MIN_CHARS else '不达标'}")
    print(f"小标题：{len(subs)} 个 → {'达标' if len(subs) >= 3 else '不达标'}（{ '；'.join(subs) }）")
    print(f"具体数据：正文出现数字 {stats['data_points']} 处 → {'达标' if stats['data_points'] >= 5 else '不达标'}")
    print(f"finish_reason：{stats['finish_reason']} → "
          f"{'未被截断，正常收尾' if stats['finish_reason'] == 'stop' else '异常'}")
    print(f"结尾完整性：{'以完整句子收尾' if ends_complete(text) else '疑似半截'}")
    print("结论：✅ 简报内容完整、字数达标、结构齐备，可直接放入周报。")
    print("（提示：以上内容由 GLM 基于模型知识生成，关键数字建议在对外使用前复核。）")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未检测到环境变量 ZHIPUAI_API_KEY。请先设置：export ZHIPUAI_API_KEY=<你的Key>",
              file=sys.stderr)
        return 1

    strategies = [
        ("glm-5.3 整篇生成", strategy_whole),
        ("glm-5.2 关闭思考重试", strategy_no_thinking),
        ("分段生成后拼接", strategy_segmented),
    ]
    for name, strategy in strategies:
        log(f"→ 尝试{name}")
        text = strategy(api_key)
        if text is None:
            log(f"← {name}未产出合格结果，转向下一策略")
            continue
        _, _, stats = validate(text, "stop")
        deliver(text, stats)
        return 0

    print("错误：三种策略均未能生成完整达标的简报（未输出任何半截内容）。"
          "请检查网络、Key 余额与平台控制台配额后重试。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
