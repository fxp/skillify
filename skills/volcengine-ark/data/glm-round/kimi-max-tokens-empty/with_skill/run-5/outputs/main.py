#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火山方舟 Agent Plan · kimi-k3 情感分类（单次调用，输出上限尽量压到 64 token）

接入要点（三套入口互不通用，本脚本只走 Agent Plan 这一套）：
  Base URL  https://ark.cn-beijing.volces.com/api/plan/v3
            （不要用 /api/v3：Agent Plan 专属 Key 打 /api/v3 直接 401，方舟 Key 打则产生后付费费用）
  API Key   环境变量 ARK_AGENT_PLAN_API_KEY —— Agent Plan 控制台「使用配置 → 配置专属API Key」
            里那把专属 Key，与方舟 API Key / Coding Plan Key 均不通用
  model     kimi-k3（小写 Model Name；需要 Agent Plan Medium 及以上档位，Small 档返回 404）
  role      只能用 system / user / assistant / tool（不支持 developer，否则 400）

为什么不能简单写 "max_tokens": 64 —— 这是 kimi-k3 的一个实测坑（2026-09-04 真实 API 验证）：
  kimi-k3 默认开启深度思考，且思维链 token 计入 max_tokens 额度：
  max_tokens=64 → finish_reason="length"、content=""（思维链就吃掉 61 token，回答被截成空）。
  正确写法是 max_completion_tokens（上限 = 思维链 + 回答，取值 [1, 65536]，不能与 max_tokens 同传）。
  而「关思考」（thinking.disabled）与「压低思考」（reasoning_effort=low）对 kimi-k3 是否生效
  官方未说明、也未实测过（glm-5.3 上前者直接 400、后者等效关思考），所以本脚本按阶梯策略
  逐个尝试、每一步都校验「真的拿到了分类结果」，拿不到就如实说明原因：

  策略 1  thinking=disabled + max_completion_tokens=64   若 kimi-k3 支持关思考 → 64 上限内直接出结果
  策略 2  reasoning_effort=low + max_completion_tokens=64 若能压低思考 → 仍守 64 上限
  策略 3  默认思考 + max_completion_tokens=512           实测可稳定拿到回答的写法；
                                                          放宽 64 上限换「必须拿到结果」，并如实报告

依赖：仅 requests（pip install requests）。运行：python3 main.py
"""

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
CHAT_COMPLETIONS_URL = BASE_URL + "/chat/completions"
MODEL = "kimi-k3"
TEXT_TO_CLASSIFY = "这家店的服务态度太差了，再也不来了"
ALLOWED_LABELS = ("正面", "负面", "中性")
OUTPUT_TOKEN_CAP = 64                 # 用户要求的输出上限
FALLBACK_MAX_COMPLETION_TOKENS = 512  # 64 压不住时的兜底上限（kimi-k3 最大输出 128k，512 依旧极省）
REQUEST_TIMEOUT_SECONDS = 120         # 深度思考模型的非流式调用偏慢，超时给足

MESSAGES = [
    {
        "role": "system",
        "content": (
            "你是情感分类器。判断用户给出的文本的情感倾向，"
            "只输出「正面」「负面」「中性」三个词中的一个，"
            "不要输出任何解释、标点或其他文字。"
        ),
    },
    {"role": "user", "content": "待分类文本：" + TEXT_TO_CLASSIFY},
]

# 阶梯策略：params 会并入请求体（注意：永远不带 max_tokens，只带 max_completion_tokens）；
# within_cap 表示该策略是否仍守住 64 token 的输出上限。
ATTEMPTS = [
    {
        "name": f"策略1 thinking=disabled + max_completion_tokens={OUTPUT_TOKEN_CAP}",
        "params": {
            "thinking": {"type": "disabled"},
            "max_completion_tokens": OUTPUT_TOKEN_CAP,
        },
        "within_cap": True,
    },
    {
        "name": f"策略2 reasoning_effort=low + max_completion_tokens={OUTPUT_TOKEN_CAP}",
        "params": {
            "reasoning_effort": "low",
            "max_completion_tokens": OUTPUT_TOKEN_CAP,
        },
        "within_cap": True,
    },
    {
        "name": f"策略3 默认思考 + max_completion_tokens={FALLBACK_MAX_COMPLETION_TOKENS}",
        "params": {
            "max_completion_tokens": FALLBACK_MAX_COMPLETION_TOKENS,
        },
        "within_cap": False,
    },
]


def extract_label(text):
    """从模型输出里提取 正面/负面/中性；无法唯一确定时返回 None。"""
    cleaned = text.strip().strip("「」『』“”\"'。！!？?，, \t\r\n")
    if cleaned in ALLOWED_LABELS:
        return cleaned
    hits = [label for label in ALLOWED_LABELS if label in text]
    return hits[0] if len(hits) == 1 else None


def parse_error(resp):
    """把非 2xx 响应解析成 (code, message)。错误体固定为 {"error":{code,message,param,type}}，
    但部分 404 的 body 可能为空，解析要兜底。程序判别用 error.code，不要解析 message。"""
    try:
        err = resp.json().get("error") or {}
        return err.get("code") or "", err.get("message") or (resp.text or "")[:300]
    except ValueError:
        return "", (resp.text or "").strip()[:300] or "(空 body)"


def explain_error(status, code):
    """把已知错误码翻译成明确的排查指引（正文附 API 原文，二者都会打印）。"""
    if status == 401 or code == "AuthenticationError":
        return (
            "鉴权失败：Agent Plan 专属 Key 只在 /api/plan* 入口有效。\n"
            "  - 确认 ARK_AGENT_PLAN_API_KEY 是 Agent Plan 控制台「使用配置 → 配置专属API Key」\n"
            "    里的那把（拿方舟 API Key / Coding Plan Key 打这个入口同样报 401）；\n"
            "  - 确认 Key 复制时没带首尾空格（本脚本已自动 strip 并用 Bearer 头发送）。"
        )
    if status == 404 and code == "UnsupportedModel":
        return (
            "模型不可用：kimi-k3 需要 Agent Plan Medium 及以上档位（Small 档没有这个模型），\n"
            "  且 Plan 入口只能填小写 Model Name（本脚本已填 kimi-k3）。请升配套餐或换套餐内模型。"
        )
    if status == 429 or code == "QuotaExceeded":
        return (
            "套餐额度耗尽（5 小时 / 周 / 月 AFP 任一触顶都会报 429 QuotaExceeded）。\n"
            "  注意 kimi-k3 不支持超额后付费，只能等额度刷新，\n"
            "  或临时换成 doubao-seed-2.0-mini / deepseek-v4-flash 等支持超额后付费的模型。"
        )
    if status == 400 and code == "InvalidSubscription":
        return "无有效套餐订阅（400 InvalidSubscription），请到 Agent Plan 控制台确认订阅状态。"
    if status == 400 and code == "SensitiveContentDetected":
        return "输入文本被内容审核拦截（400 SensitiveContentDetected），请更换待分类文本。"
    return f"HTTP {status}，错误码 {code or '(无)'}。请把下面的 API 原文拿去对照方舟错误码文档排查。"


def is_unsupported_knob(status, code, message):
    """400 且明确指向本次正在试的思考开关参数 → 说明 kimi-k3 不吃这个参数，
    属于预期内的「策略不可用」，换下一个策略；其余错误换参数也救不了，直接终止。"""
    if status != 400 or code not in ("InvalidParameter", "InvalidArgumentError"):
        return False
    msg = message.lower()
    return "thinking" in msg or "reasoning_effort" in msg


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "未拿到分类结果：环境变量 ARK_AGENT_PLAN_API_KEY 未设置。\n"
            "  请到 Agent Plan 控制台「使用配置 → 配置专属API Key」获取专属 Key\n"
            "  （与方舟 API Key 不通用），然后 export ARK_AGENT_PLAN_API_KEY=<Key> 后重跑。"
        )

    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    failures = []  # 每个失败策略的原因，用于最终如实汇报
    for attempt in ATTEMPTS:
        payload = {"model": MODEL, "messages": MESSAGES}
        payload.update(attempt["params"])

        try:
            resp = requests.post(
                CHAT_COMPLETIONS_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            sys.exit(f"未拿到分类结果：请求 Agent Plan 入口失败（网络层错误）。\n  {exc!r}")

        if resp.status_code != 200:
            code, message = parse_error(resp)
            if is_unsupported_knob(resp.status_code, code, message):
                print(f"[{attempt['name']}] 该参数不被 kimi-k3 支持，换下一策略。")
                print(f"  API 原文：{message}")
                failures.append(f"{attempt['name']}: 参数被模型拒绝（{message}）")
                continue
            sys.exit(
                f"未拿到分类结果：[{attempt['name']}] 调用失败。\n"
                f"  {explain_error(resp.status_code, code)}\n"
                f"  API 原文：{message}"
            )

        try:
            data = resp.json()
            choice = data["choices"][0]
            content = ((choice.get("message") or {}).get("content") or "").strip()
            finish_reason = choice.get("finish_reason")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            sys.exit(
                f"未拿到分类结果：[{attempt['name']}] 返回 200 但响应结构异常。\n"
                f"  body 前 500 字：{resp.text[:500]}"
            )

        completion_tokens = usage.get("completion_tokens")
        reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

        # 关键校验：kimi-k3 的思维链计入输出额度，64 的上限很容易被思维链吃光，
        # 返回 200 也不代表拿到了结果——必须检查 finish_reason 和 content 非空。
        if finish_reason == "length" or not content:
            print(f"[{attempt['name']}] 输出被长度上限截断，回答为空，拿不到结果，换下一策略。")
            print(
                f"  finish_reason={finish_reason}, content={content!r}, "
                f"reasoning_tokens={reasoning_tokens}, completion_tokens={completion_tokens}"
            )
            failures.append(
                f"{attempt['name']}: 输出额度被思维链耗尽"
                f"（finish_reason=length，reasoning_tokens={reasoning_tokens}，"
                f"completion_tokens={completion_tokens}，content 为空）"
            )
            continue

        label = extract_label(content)
        if label is None:
            sys.exit(
                f"未拿到分类结果：[{attempt['name']}] 模型输出无法识别为三个标签之一。\n"
                f"  原始输出：{content!r}"
            )

        # ---- 真的拿到了分类结果，如实报告成本与 64 上限是否守住 ----
        print(f"[{attempt['name']}] 成功，模型输出：{content!r}")
        print(
            f"  实际用量：completion_tokens={completion_tokens}"
            f"（其中思维链 reasoning_tokens={reasoning_tokens}）"
        )
        if attempt["within_cap"]:
            print(f"  [成本] 输出上限 ≤{OUTPUT_TOKEN_CAP} token 的要求已满足。")
        else:
            print(
                f"  [成本] 输出上限未能压到 {OUTPUT_TOKEN_CAP} token 以内，"
                f"已放宽到 {FALLBACK_MAX_COMPLETION_TOKENS}，原因："
            )
            print(
                "  - kimi-k3 默认开启深度思考，且思维链 token 计入输出额度"
                "（实测设 64 上限时思维链就吃光额度，content 为空、finish_reason=length）"
            )
            for failure in failures:
                print(f"  - {failure}")
            print(
                f"  - 即 {OUTPUT_TOKEN_CAP} token 上限与「必须拿到分类结果」在 kimi-k3 上不可兼得，"
                "按你的优先级选择保结果、放宽上限（512 依旧远小于模型 128k 最大输出）。"
            )
        print()
        print("情感分类结果：")
        print(label)
        return

    sys.exit(
        "未拿到分类结果：三个策略全部失败，未打印任何空结果冒充成功。\n失败原因：\n"
        + "\n".join(f"  - {failure}" for failure in failures)
    )


if __name__ == "__main__":
    main()
