#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用火山方舟 Agent Plan 的 kimi-k3 给一条评语做情感分类（正面/负面/中性）。

写脚本前查过的官方文档事实，它们决定了下面的调用策略：
  1. Kimi K3 是"始终思考"的模型：官方 FAQ 明确"思维链目前关不了"，
     对这类专属思考模型传 thinking.type=disabled 会被服务端拒绝（400）。
  2. 方舟 Chat API 的 max_tokens 同时限制"正文 + 思维链(reasoning)"，
     思考 token 也计入输出额度。
     —— 因此 max_tokens=64 时，额度大概率全被思维链耗尽：
        choices[0].message.content 为空、finish_reason=max_tokens，
        这就是"想省钱反而拿不到结果"的坑，本脚本必须识别并如实上报。
  3. K3 支持顶层 reasoning_effort=low/high/max（默认 max），low 可显著缩短思维链。

调用策略（成本优先，但必须真的拿到分类词；拿不到就把每次的原因讲清楚）：
    ① max_tokens=64   + thinking disabled      万一接入点允许关思考，一词回复装得下 64 token；
    ② max_tokens=64   + reasoning_effort=low   仍按 ≤64 试一次最低强度思考；
    ③ max_tokens=1024 + reasoning_effort=low   放开上限换真实结果（预期在此成功）；
    ④ max_tokens=4096 + reasoning_effort=low   兜底，防个别请求思维链异常变长。
  任何一步拿到合法分类词立即停止；全程记录 finish_reason 与 token 用量；
  四步全失败则逐条打印失败原因、以退出码 1 结束，绝不输出空结果冒充成功。

用法：
    export ARK_AGENT_PLAN_API_KEY=<Agent Plan 的 API Key>
    python3 main.py
可选环境变量：
    ARK_BASE_URL  默认 https://ark.cn-beijing.volces.com/api/v3
    ARK_MODEL     默认 kimi-k3；若控制台里实际的 Model ID 带日期后缀
                  （如 kimi-k3-xxxxxx），用同名值覆盖即可。
"""

import json
import os
import re
import sys

import requests

TEXT_TO_CLASSIFY = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
MODEL = os.environ.get("ARK_MODEL", "kimi-k3")
REQUEST_TIMEOUT = 120  # 秒；思考模型生成耗时较长，留足余量

SYSTEM_PROMPT = (
    "你是情感分类器。判断用户给出的评语的情感倾向，"
    "只回答「正面」「负面」「中性」三个词中的一个，"
    "不要解释、不要标点、不要输出其他任何文字。"
)

# 逐级尝试的请求参数（策略见文件头）。params 里只放会真正发到 API 的字段。
ATTEMPTS = [
    {"params": {"max_tokens": 64, "thinking": {"type": "disabled"}},
     "note": "先试关闭思考：若允许关思考，一个词的回复完全装得下 64 token"},
    {"params": {"max_tokens": 64, "reasoning_effort": "low"},
     "note": "仍按 ≤64 试一次：最低推理强度，看思维链能否短到塞进 64 token"},
    {"params": {"max_tokens": 1024, "reasoning_effort": "low"},
     "note": "放开输出上限，用最低推理强度换真实结果（预期在这里成功）"},
    {"params": {"max_tokens": 4096, "reasoning_effort": "low"},
     "note": "兜底：防个别请求思维链异常变长"},
]


def extract_label(text):
    """从模型回复中提取分类词：整句匹配优先；否则三个词恰好出现一个才认。"""
    if not text:
        return None
    stripped = re.sub(r"[\s「」『』“”\"'。．.！!？?：:，,]", "", text)
    if stripped in LABELS:
        return stripped
    hits = [label for label in LABELS if label in stripped]
    return hits[0] if len(hits) == 1 else None


def describe_params(params):
    parts = ["max_tokens=%s" % params["max_tokens"]]
    if "thinking" in params:
        parts.append("thinking=%s" % params["thinking"]["type"])
    if "reasoning_effort" in params:
        parts.append("reasoning_effort=%s" % params["reasoning_effort"])
    return "，".join(parts)


def build_payload(params):
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "评语：" + TEXT_TO_CLASSIFY},
        ],
        **params,
    }


def parse_error(resp):
    """把错误响应压成一行可读文本。"""
    try:
        err = (resp.json() or {}).get("error") or {}
        return "HTTP %s code=%s message=%s" % (resp.status_code, err.get("code"), err.get("message"))
    except ValueError:
        return "HTTP %s（非 JSON 响应）%s" % (resp.status_code, resp.text[:200])


def call_model(session, api_key, params, unsupported):
    """按给定参数调用一次 Chat API。

    返回 (label, diag)：label 为「正面/负面/中性」之一，拿不到则为 None，
    此时 diag["reason"] 一定写明本次失败的具体原因。
    unsupported 是跨尝试共享的集合，记录已被服务端明确拒绝的参数名，
    后续尝试会自动剔除，避免反复撞同一个 400。
    """
    for _ in range(2):  # 最多两轮：首轮 400 指向某参数时，剔除后补发一轮
        effective = {k: v for k, v in params.items() if k not in unsupported}
        try:
            resp = session.post(
                BASE_URL + "/chat/completions",
                headers={"Authorization": "Bearer " + api_key},
                json=build_payload(effective),
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            return None, {"reason": "网络请求失败：%r" % exc}

        if resp.status_code == 400:
            try:
                msg = str((resp.json().get("error") or {}).get("message", ""))
            except ValueError:
                msg = resp.text[:200]
            dropped = False
            for key, hints in (("thinking", ("thinking", "思考")),
                               ("reasoning_effort", ("reasoning_effort", "推理强度"))):
                if key in effective and any(h in msg for h in hints):
                    unsupported.add(key)
                    dropped = True
                    print("  !! 服务端拒绝了 %s 参数（400：%s），已自动剔除后重试" % (key, msg[:120]))
            if dropped:
                continue
            return None, {"reason": "请求被拒绝（400）：" + (msg or resp.text[:300])}
        if resp.status_code in (401, 403):
            return None, {"reason": "鉴权失败（%s）：请检查 %s 是否为有效的 Agent Plan API Key。%s"
                                    % (resp.status_code, API_KEY_ENV, resp.text[:200])}
        if resp.status_code == 404:
            return None, {"reason": "接口或模型不存在（404）：请确认套餐包含 %s、模型 ID 正确"
                                    "（可用环境变量 ARK_MODEL 覆盖）。%s" % (MODEL, resp.text[:200])}
        if resp.status_code == 429:
            return None, {"reason": "触发限流（429），稍后重试即可。%s" % resp.text[:200]}
        if resp.status_code != 200:
            return None, {"reason": parse_error(resp)}

        try:
            data = resp.json()
        except ValueError:
            return None, {"reason": "HTTP 200 但响应不是 JSON：%s" % resp.text[:200]}

        choices = data.get("choices") or []
        if not choices:
            return None, {"reason": "HTTP 200 但响应没有 choices：%s"
                                    % json.dumps(data, ensure_ascii=False)[:300]}
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        reasoning_tokens = details.get("reasoning_tokens", usage.get("reasoning_tokens"))

        diag = {
            "content": content,
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": reasoning_tokens,
        }
        label = extract_label(content)
        if label:
            return label, diag

        if not content.strip():
            if finish in ("max_tokens", "length"):
                diag["reason"] = (
                    "输出为空、finish_reason=%s：max_tokens=%s 的额度全部被思维链消耗"
                    "（reasoning 约 %s token / %s 字，正文 content 为空）——"
                    "思考模型要等思维链写完才开始写正文，额度不够时正文一个字都出不来。"
                    % (finish, effective.get("max_tokens"),
                       reasoning_tokens if reasoning_tokens is not None else "?",
                       len(reasoning)))
            else:
                diag["reason"] = "输出为空、finish_reason=%s（content 与 reasoning_content 均为空）" % finish
        else:
            diag["reason"] = "模型回复中找不到唯一的分类词，回复原文：%r" % content[:80]
        return None, diag

    return None, {"reason": "内部错误：剔除被拒参数后仍失败"}


def list_kimi_models(session, api_key):
    """失败时的辅助诊断：尝试列出该 Key 可用的模型（并非所有部署都开放此接口，失败就跳过）。"""
    try:
        resp = session.get(
            BASE_URL + "/models",
            headers={"Authorization": "Bearer " + api_key},
            timeout=15,
        )
        data = resp.json()
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        kimi = [i for i in ids if "kimi" in i.lower()]
        if kimi:
            return "该 Key 可用、名字含 kimi 的模型：" + "、".join(kimi)
        if ids:
            return "该 Key 可用的 %d 个模型里没有名字含 kimi 的，前若干个：%s" % (
                len(ids), "、".join(ids[:10]))
        return "模型列表接口返回为空。"
    except Exception as exc:  # 诊断用途，任何失败都不影响主流程
        return "模型列表接口不可用或查询失败（%r），请到方舟控制台核对。" % exc


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        sys.stderr.write("错误：未设置环境变量 %s。\n" % API_KEY_ENV)
        sys.stderr.write("请先执行 export %s=<你的火山方舟 Agent Plan API Key>，再运行 python3 main.py\n"
                         % API_KEY_ENV)
        return 1

    print("待分类评语：%s" % TEXT_TO_CLASSIFY)
    print("模型：%s    接口：%s/chat/completions" % (MODEL, BASE_URL))
    print("目标：尽量把单次输出压在 64 token 内，同时必须真的拿到「正面/负面/中性」之一\n")

    session = requests.Session()
    unsupported = set()
    history = []  # [(序号, 参数, 失败原因)]
    label, won = None, None

    for idx, attempt in enumerate(ATTEMPTS, 1):
        params = attempt["params"]
        print("[尝试 %d/%d] %s（%s）" % (idx, len(ATTEMPTS), describe_params(params), attempt["note"]))
        label, diag = call_model(session, api_key, params, unsupported)
        if label:
            won = (idx, params, diag)
            print("  -> 成功：模型回复 %r，归一化为「%s」\n" % (diag["content"], label))
            break
        history.append((idx, params, diag["reason"]))
        print("  -> 未拿到结果：%s\n" % diag["reason"])

    if label:
        idx, params, diag = won
        print("=" * 13, "情感分类结果", "=" * 13)
        print(label)
        print("=" * 35)
        completion = diag.get("completion_tokens")
        reasoning = diag.get("reasoning_tokens")
        print("第 %d 次尝试成功：%s；实际输出 %s token（其中思维链约 %s token）。"
              % (idx, describe_params(params),
                 completion if completion is not None else "未知",
                 reasoning if reasoning is not None else "未知"))
        if params["max_tokens"] <= 64:
            print("已满足「单次输出 ≤64 token」的成本目标。")
        else:
            print("注意：成功这次超出了 64 token 的原始目标，原因如下——")
            print("  kimi-k3 是始终思考的模型（官方明确思维链无法关闭），而方舟的 max_tokens")
            print("  同时限制正文与思维链：64 个 token 连思维链都装不下，正文必然为空。实测证据：")
            for i, p, reason in history:
                print("  * 尝试 %d（%s）：%s" % (i, describe_params(p), reason))
        return 0

    # 四次尝试全部失败：如实交代每一次的原因，绝不输出空结果冒充成功
    print("未能拿到分类结果。各次尝试的失败原因：")
    for i, p, reason in history:
        print("  尝试 %d（%s）：%s" % (i, describe_params(p), reason))
    print()
    print("排查建议：")
    print("  1) 401/403 → %s 不是有效的 Agent Plan Key，或无权访问该模型。" % API_KEY_ENV)
    print("  2) 404/模型不存在 → 你的套餐档位可能不含 kimi-k3（官方标注仅部分档位支持），")
    print("     或 Model ID 与控制台不一致；确认后用 ARK_MODEL 环境变量覆盖。")
    print("     自动核对：%s" % list_kimi_models(session, api_key))
    print("  3) 429 → 限流，稍等重试；网络错误 → 检查本机到 ark.cn-beijing.volces.com 的连通性。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
