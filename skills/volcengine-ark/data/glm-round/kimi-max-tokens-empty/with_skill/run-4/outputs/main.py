#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan · kimi-k3 情感分类。

对"这家店的服务态度太差了，再也不来了"判断情感，stdout 只打印「正面」「负面」「中性」
三个词之一；全部过程、用量与失败原因走 stderr。

用法：
    export ARK_AGENT_PLAN_API_KEY=<Agent Plan 控制台"配置专属API Key"生成的 Key>
    python3 main.py

设计依据（volcengine-ark skill 2026-09-04 对 Agent Plan 入口 /api/plan/v3 + kimi-k3
的真实 API 实测，及官方文档 docs.volcengine.com/docs/82379/1449737、1494384）：

1. Agent Plan 专属 Key 只能打 /api/plan/v3（打 /api/v3、/api/coding/v3 一律 401）；
   model 填小写 Model Name "kimi-k3"（Small 档不可用，需 Medium 及以上套餐）。
2. kimi-k3 默认开启思考，且它的输出上限把思维链也计入：
   - 传 max_tokens: 64 实测得到 finish_reason="length"、content=""（思维链 61 token
     吃光 64 的额度，回答被截空）——所以本脚本绝不传 max_tokens；
   - max_completion_tokens 才是正确写法：限制"思维链 + 回答"的总长，[1, 65536]，
     官方文档明确"不可与 max_tokens 字段同时设置"。
3. thinking.disabled 的官方支持清单不含 kimi-k3（glm-5.3 实测传了直接 400），
   reasoning_effort 各档对 kimi-k3 也未验证。因此无法假设思考能关掉或压短，
   采用三级降级：先严格把输出压进 64 token；拿不到分类结果时按"结果优先"
   放宽上限，并把为什么压不进 64、实际输出多少 token 原原本本告诉用户。

另注：Agent Plan 官方口径"文本模型不可用于 API 调用"（使用条款限制，技术上可调），
生产环境大量直调有被判滥用的风险。
"""

import os
import sys

import requests

API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
MODEL = "kimi-k3"
TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")
OUTPUT_LIMIT = 64     # 用户要求：本次调用输出上限 <= 64 token
FALLBACK_LIMIT = 512  # 思考压不进 64 时给思维链留的余量（仍远小于默认 4096）
TIMEOUT = 180         # 官方建议：思考场景放大非流式超时

PROMPT = (
    "情感分类任务：判断下面这句话的情感倾向。\n"
    f"句子：{TEXT}\n"
    "只输出「正面」「负面」「中性」三个词中的一个，"
    "不要输出解释、标点、序号或任何其他文字。"
)

# 降级链：前两级严格满足 64 token 上限；最后一级拿到结果优先。
STRATEGIES = [
    {
        "name": "策略1｜关闭思考 thinking.disabled + max_completion_tokens=64",
        "params": {"thinking": {"type": "disabled"}, "max_completion_tokens": OUTPUT_LIMIT},
        "within_limit": True,
    },
    {
        "name": "策略2｜最低思考档 reasoning_effort=low + max_completion_tokens=64",
        "params": {"reasoning_effort": "low", "max_completion_tokens": OUTPUT_LIMIT},
        "within_limit": True,
    },
    {
        "name": "策略3｜默认思考 + max_completion_tokens=512（拿到结果优先）",
        "params": {"max_completion_tokens": FALLBACK_LIMIT},
        "within_limit": False,
    },
]


def log(msg):
    """过程与诊断信息走 stderr，保证 stdout 只有最终分类词。"""
    print(msg, file=sys.stderr)


def fail(msg):
    log("\n[失败] 没有拿到分类结果。原因：\n" + msg)
    sys.exit(1)


def extract_label(content):
    """从模型输出中提取三个分类词之一；提取不到返回 None。

    先做整串精确匹配，再按 LABELS 顺序做包含匹配（容忍"负面。"、"答案：负面"这类
    带了杂字的输出）。prompt 已严格限制输出，这里只是兜底。
    """
    text = (content or "").strip()
    if text in LABELS:
        return text
    for label in LABELS:
        if label in text:
            return label
    return None


def explain_http_error(status, body):
    """把非 200 响应翻译成人能看懂的原因，附 API 原始报错。"""
    err = (body or {}).get("error") or {}
    code = err.get("code") or ""
    message = err.get("message") or ""
    raw = resp_snippet(body)
    hints = {
        "AuthenticationError": (
            "鉴权失败：ARK_AGENT_PLAN_API_KEY 无效，或用的不是 Agent Plan 专属 Key"
            "（它打 /api/v3 等其他入口同样会 401；与方舟 API Key 不通用）。"
        ),
        "UnsupportedModel": (
            "模型不可用：kimi-k3 不在当前套餐支持范围（Agent Plan Small 档不可用"
            " kimi-k3，需 Medium 及以上），或该模型已下线。"
        ),
    }
    hint = hints.get(code, "调用被服务端拒绝（换参数通常无效）。")
    if status == 429 and not hint:
        hint = "限流或套餐额度不足：Agent Plan 额度分 5 小时/周/月三档刷新。"
    return f"HTTP {status} {code}: {hint}\n        API 原始报错: {raw or message}"


def resp_snippet(body):
    """响应里 error.message 之外的兜底：截一段原文便于排查。"""
    if not body:
        return ""
    err = body.get("error") or {}
    return err.get("message") or str(body)[:300]


def chat(api_key, params):
    """POST 一次 Chat Completions，返回 (status_code, 解析后的 JSON 或 None)。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        # 注意：绝不传 max_tokens——kimi-k3 的 max_tokens 计入思维链，
        # 64 会把回答截成空串（skill 实测）。上限统一走 max_completion_tokens。
    }
    payload.update(params)
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        fail("网络请求失败（无法连到 %s）：%r" % (API_URL, exc))
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        fail(
            "环境变量 ARK_AGENT_PLAN_API_KEY 未设置。请先在 Agent Plan 控制台"
            "「配置专属API Key」拿到专属 Key 再 export（它和方舟 API Key 不通用）。"
        )

    failures = []  # 每一级失败的原因，最终如实汇报
    label = None

    for idx, strategy in enumerate(STRATEGIES):
        last = idx == len(STRATEGIES) - 1
        log("=== %s ===" % strategy["name"])

        status, body = chat(api_key, strategy["params"])

        if status != 200:
            reason = explain_http_error(status, body)
            # 400 = 某个参数不被 kimi-k3 接受（最可能是 thinking/reasoning_effort），
            # 换下一级参数还有机会；401/404/429/5xx 换参数也没用，直接失败并说明。
            failures.append("%s：%s" % (strategy["name"], reason))
            if status == 400 and not last:
                log("[跳过] " + reason)
                continue
            fail("\n  ".join(failures))

        choices = (body or {}).get("choices") or []
        if not choices:
            failures.append("%s：响应 200 但没有 choices：%s" % (strategy["name"], resp_snippet(body)))
            if last:
                fail("\n  ".join(failures))
            log("[跳过] 响应中没有 choices。")
            continue

        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish = choice.get("finish_reason")
        usage = (body or {}).get("usage") or {}
        completion = usage.get("completion_tokens")
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        served_model = body.get("model") or MODEL

        label = extract_label(content)
        if label is None:
            # 最典型的失败：finish_reason=length 且 content 为空——思维链把
            # max_completion_tokens 的额度吃光，回答被截空（正是本任务要防的坑）。
            if not content.strip():
                detail = (
                    "回答为空：finish_reason=%s，completion_tokens=%s（其中思维链 %s token）"
                    % (finish, completion, reasoning)
                )
                if finish == "length":
                    detail += "——上限被思维链耗尽，kimi-k3 的输出上限参数计入思维链。"
            elif finish == "content_filter":
                detail = "输出被内容审核拦截（finish_reason=content_filter）。"
            else:
                detail = "输出「%s」里找不到三个分类词之一（finish_reason=%s）。" % (
                    content.strip()[:50], finish,
                )
            failures.append("%s：%s" % (strategy["name"], detail))
            if last:
                fail("\n  ".join(failures))
            log("[未拿到结果] " + detail)
            continue

        # ---- 拿到分类结果 ----
        answer_tokens = None if completion is None else completion - reasoning
        log("[调用成功] 实际服务模型=%s，finish_reason=%s" % (served_model, finish))
        log("[用量] completion_tokens=%s（思维链 %s + 回答 %s）"
            % (completion if completion is not None else "未知", reasoning,
               answer_tokens if answer_tokens is not None else "未知"))
        if strategy["within_limit"]:
            log("[成本] 满足要求：输出上限压在 %d token 内，且拿到了分类结果。" % OUTPUT_LIMIT)
        else:
            log("[成本说明] 未能把输出上限压到 %d token，已放宽到 %d。原因：" %
                (OUTPUT_LIMIT, FALLBACK_LIMIT))
            for f in failures:
                log("  - " + f)
            log("  即：kimi-k3 的输出上限参数 max_completion_tokens 计入思维链，思考默认开启")
            log("  且压不进 %d token（关不掉/压不短，或压短后 64 仍装不下思维链+回答），" % OUTPUT_LIMIT)
            log("  在「必须拿到分类结果」的前提下只能放宽；本次实际输出 %s token。"
                % (completion if completion is not None else "未知"))
        print(label)  # stdout：只有最终分类词
        return

    fail("所有策略都未返回分类结果：\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
