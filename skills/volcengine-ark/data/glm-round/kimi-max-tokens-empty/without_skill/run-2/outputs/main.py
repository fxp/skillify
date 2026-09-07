#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用火山方舟 Agent Plan 的 kimi-k3 做情感三分类（正面 / 负面 / 中性）。

用法：
    export ARK_AGENT_PLAN_API_KEY="ark-xxxxxxxx"   # 方舟控制台『API Key 管理』创建
    python3 main.py

成功时 stdout 只输出分类结果（正面/负面/中性 之一），过程信息走 stderr。

设计要点（也是最容易翻车的两处）：
1. Agent Plan 的 OpenAI 兼容入口是 https://ark.cn-beijing.volces.com/api/plan/v3
   （订阅套餐专用；常规按量入口是 /api/v3，脚本里仅作 404 兜底）。
2. kimi-k3 默认开深度思考，而方舟的思考(reasoning) token 同样计入 max_tokens。
   本次把输出上限压到 64 token，如果放任模型思考，思维链会把 64 个 token 烧光，
   返回的 content 为空、finish_reason=length —— 接口“成功”但其实什么都没拿到。
   因此必须显式传 thinking={"type": "disabled"}，并对空结果做显式诊断：
   拿不到分类结果时以非 0 码退出并说明原因，绝不打印空结果了事。

可选环境变量：
    ARK_MODEL     模型 ID，默认 kimi-k3（Agent Plan 里模型 ID 是短名，如 kimi-k2.6）
    ARK_BASE_URL  手动指定 Base URL（默认先试 Agent Plan 入口，404 再试常规入口）
"""

import json
import os
import sys
import time

import requests

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
MODEL = os.environ.get("ARK_MODEL", "").strip() or "kimi-k3"

# Agent Plan（OpenAI 兼容）专用入口在前，常规按量入口兜底
DEFAULT_BASE_URLS = [
    "https://ark.cn-beijing.volces.com/api/plan/v3",
    "https://ark.cn-beijing.volces.com/api/v3",
]

MAX_TOKENS = 64       # 单次调用输出 token 上限（成本约束）
REQUEST_TIMEOUT = 60  # 秒

TEXT = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的评论判断情感倾向，"
    "只回复「正面」「负面」「中性」三个词之一，"
    "不要解释、不要标点、不要换行、不要输出任何其他内容。"
)
USER_PROMPT = "评论：%s\n请回复分类结果：" % TEXT


def info(msg):
    print("[info] %s" % msg, file=sys.stderr)


def fail(reason, detail=""):
    """明确报告“没拿到结果”及原因，非 0 码退出。"""
    print("[未取得分类结果] %s" % reason, file=sys.stderr)
    if detail:
        print("[详情] %s" % detail, file=sys.stderr)
    sys.exit(1)


def post_chat(session, base_url, api_key, payload):
    """POST {base_url}/chat/completions，自动处理两类可恢复的错误：
    - 400 且报错提到 thinking：该模型不支持此参数，去掉后重试一次；
    - 429：限流，歇 2 秒重试一次。
    返回 requests.Response，网络异常向上抛。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    retried_429 = False
    while True:
        resp = session.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 400 and "thinking" in payload and "thinking" in resp.text:
            payload = {k: v for k, v in payload.items() if k != "thinking"}
            info("服务端拒绝 thinking 参数（可能不支持显式关闭思考），已去掉该参数重试")
            continue
        if resp.status_code == 429 and not retried_429:
            retried_429 = True
            info("触发限流（429），2 秒后重试")
            time.sleep(2)
            continue
        return resp


def list_kimi_models(session, base_url, api_key):
    """Best-effort 诊断：查 OpenAI 兼容的 /models，返回名字带 kimi 的模型 ID。"""
    try:
        resp = session.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": "Bearer " + api_key},
            timeout=15,
        )
        data = resp.json()
        ids = [m.get("id") for m in data.get("data", [])]
        return [i for i in ids if i and "kimi" in str(i).lower()]
    except Exception:  # 诊断用途，失败就放弃，不影响主流程
        return []


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        fail(
            "环境变量 %s 未设置。请在火山方舟控制台『API Key 管理』创建 Agent Plan 的 "
            "API Key（ark- 开头）后重试。" % API_KEY_ENV
        )

    override = os.environ.get("ARK_BASE_URL", "").strip()
    base_urls = [override] if override else DEFAULT_BASE_URLS

    # 关键参数：
    # - max_tokens=64：输出（含思考 token）硬性压在 64 token 以内
    # - thinking disabled：kimi-k3 默认深度思考且思考 token 计入 max_tokens，
    #   不关掉的话 64 个 token 会被思维链耗尽，正文 content 返回为空
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
        "stream": False,
    }

    session = requests.Session()
    resp = None
    used_base = None
    for i, base_url in enumerate(base_urls):
        last = i + 1 >= len(base_urls)
        try:
            resp = post_chat(session, base_url, api_key, payload)
        except requests.exceptions.Timeout:
            if not last:
                info("%s 请求超时，换下一个入口" % base_url)
                continue
            fail("请求 %s 超时（>%ss）。" % (base_url, REQUEST_TIMEOUT))
        except requests.exceptions.RequestException as exc:
            if not last:
                info("%s 网络错误：%s，换下一个入口" % (base_url, exc))
                continue
            fail("网络请求失败，无法连接火山方舟 API。", str(exc))
        used_base = base_url
        info("%s -> HTTP %s" % (base_url, resp.status_code))
        # 404 视为入口/模型不存在，换下一个入口再试
        if resp.status_code == 404 and not last:
            continue
        break

    if resp is None or resp.status_code != 200:
        code = resp.status_code if resp is not None else "无响应"
        body = resp.text[:800] if resp is not None else ""
        hint = ""
        if resp is not None:
            if resp.status_code in (401, 403):
                hint = "鉴权失败：确认 %s 是有效的 Agent Plan API Key。" % API_KEY_ENV
            elif resp.status_code == 404:
                hint = "接口路径或模型不存在：确认模型 ID「%s」在该套餐下可用（可用 ARK_MODEL 覆盖）。" % MODEL
            elif resp.status_code == 429:
                hint = "限流或额度不足：稍后重试，或检查套餐 AFP 额度。"
        fail("方舟 API 返回 HTTP %s，没有拿到分类结果。%s" % (code, hint), body)

    try:
        data = resp.json()
    except ValueError:
        fail("方舟 API 返回的不是合法 JSON。", resp.text[:800])

    choices = data.get("choices") or []
    if not choices:
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            extra = ""
            blob = (str(err.get("code", "")) + str(err.get("message", ""))).lower()
            if "model" in blob:  # 模型 ID 不对时，顺手列出可用的 kimi 模型
                models = list_kimi_models(session, used_base, api_key)
                if models:
                    extra = "当前入口可用的 kimi 系模型：%s（可用 ARK_MODEL 指定）" % ", ".join(models)
            fail("方舟 API 返回错误：[%s] %s %s" % (err.get("code"), err.get("message"), extra))
        fail("返回里没有 choices。", json.dumps(data, ensure_ascii=False)[:800])

    choice = choices[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

    # —— 空结果是本任务最大的坑：kimi-k3 的思考 token 计入 max_tokens，
    # 预算被思维链吃光时 content 为空。这里必须显式诊断原因，绝不静默“完成”。
    if not content:
        if finish_reason == "length" or reasoning or reasoning_tokens:
            preview = reasoning[:120] + "…" if len(reasoning) > 120 else reasoning
            fail(
                "模型正文 content 为空：max_tokens=64 的输出预算被深度思考(reasoning) token "
                "耗尽，还没轮到正文生成就被截断了。",
                "finish_reason=%r，completion_tokens=%s，reasoning_tokens=%s，思维链片段：%s。"
                "原因：kimi-k3 默认开启深度思考，且方舟的思考 token 同样计入 max_tokens；"
                "本次请求已带 thinking={'type': 'disabled'}，仍得到空正文说明该入口/该模型"
                "没有真正关闭思考。要么调大 max_tokens（会突破 64 token 成本上限），"
                "要么换支持关闭思考的模型。" % (
                    finish_reason,
                    completion_tokens,
                    reasoning_tokens,
                    preview or "（未返回思维链文本）",
                ),
            )
        if finish_reason == "content_filter":
            fail(
                "模型正文 content 为空：输出被内容安全策略拦截（finish_reason=content_filter）。",
                json.dumps(data, ensure_ascii=False)[:800],
            )
        fail("模型正文 content 为空，原因未知。", json.dumps(data, ensure_ascii=False)[:800])

    # 从回复里提取标签（取最早出现的那个词）
    hits = sorted((content.find(label), label) for label in LABELS if label in content)
    if not hits:
        fail(
            "模型有输出，但里面找不到「正面/负面/中性」任何一个词，无法给出分类结果。",
            "原始输出：%r；finish_reason=%r" % (content, finish_reason),
        )
    label = hits[0][1]

    print(label)
    info(
        "模型 %s @ %s；finish_reason=%s，completion_tokens=%s/%d（含思考 token %s）"
        % (MODEL, used_base, finish_reason, completion_tokens, MAX_TOKENS, reasoning_tokens)
    )


if __name__ == "__main__":
    main()
