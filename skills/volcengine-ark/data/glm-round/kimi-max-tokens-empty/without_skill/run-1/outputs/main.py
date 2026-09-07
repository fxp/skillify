#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用火山方舟 Agent Plan 的 kimi-k3 做情感分类（正面 / 负面 / 中性）。

为什么这个脚本要写成这样（关键背景，来自官方文档）：
  1. kimi-k3 是"始终思考"的推理模型：不支持 thinking 参数，思考无法关闭
     （官方 FAQ：K3 始终进行推理；thinking.type=disabled 只有 kimi-k2.6 等模型支持）。
  2. 思考 token 计入输出预算：官方文档明确
     "reasoning_content 的 Tokens 数 + content 的 Tokens 数 <= max_tokens"。
  3. 因此把 max_tokens 压到 64 时，思考过程本身就可能耗尽全部预算，
     表现为 content 为空、finish_reason="length"。
  本脚本的应对：
  - 用 K3 唯一的思考档位开关 reasoning_effort="low"（默认是 "max"），
    并把提示词压到最短，尽量让思考在几十个 token 内结束、留出作答空间；
  - 若 reasoning_effort 参数被网关拒绝，自动降级为不带该参数重试一次；
  - 每次请求的输出上限都严格 <= 64 token（成本封顶，最多发 2 次请求）；
  - 拿不到分类结果时，明确打印原因和证据（finish_reason / usage /
    reasoning_content 摘要），并以非零码退出，绝不打印空结果冒充成功。

用法：
    ARK_AGENT_PLAN_API_KEY=xxxx python3 main.py
可选环境变量：
    ARK_BASE_URL  覆盖网关地址（默认 https://ark.cn-beijing.volces.com/api/v3）
    ARK_MODEL     覆盖模型 ID（默认 kimi-k3；若报模型不存在，
                  请到控制台 Agent Plan 模型列表核对准确 ID 后覆盖）
"""

import json
import os
import sys

import requests

# ---------------------------- 配置 ----------------------------

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL = os.environ.get("ARK_MODEL", "kimi-k3")
MAX_TOKENS = 64  # 用户要求的硬性输出上限：<= 64 token
TIMEOUT_SECONDS = 60

TEXT_TO_CLASSIFY = "这家店的服务态度太差了，再也不来了"
LABELS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是情感分类器。判断用户句子的情感，只输出「正面」「负面」「中性」三个词之一，"
    "禁止输出解释、标点或任何其他文字。题目极简单，不要展开思考，立即作答。"
)
USER_PROMPT = "句子：%s\n情感分类结果：" % TEXT_TO_CLASSIFY


# ---------------------------- 工具函数 ----------------------------

def fail(message):
    """打印失败原因并退出。分类失败绝不算成功完成。"""
    print(message)
    sys.exit(1)


def call_model(api_key, extra_params):
    """发起一次 chat completion 调用，返回 requests.Response。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "max_tokens": MAX_TOKENS,  # 输出上限（含思考 token），严格压在 64
    }
    payload.update(extra_params)
    return requests.post(
        "%s/chat/completions" % BASE_URL,
        headers={"Authorization": "Bearer %s" % api_key},
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )


def extract_label(content):
    """从模型输出里提取分类标签。

    模型被要求只回一个词，但为稳妥仍做一层解析：
    - 内容为空 -> None
    - 恰好包含三个标签中的一个 -> 该标签
    - 同时出现多个标签或一个都没有 -> None（视为无效输出）
    """
    if not content:
        return None
    found = set(label for label in LABELS if label in content)
    return found.pop() if len(found) == 1 else None


def format_usage(usage):
    """把 usage 字段格式化成一行，作为成本证据。"""
    if not isinstance(usage, dict) or not usage:
        return "无 usage 信息"
    details = usage.get("completion_tokens_details") or {}
    parts = ["prompt_tokens=%s" % usage.get("prompt_tokens"),
             "completion_tokens=%s" % usage.get("completion_tokens"),
             "total_tokens=%s" % usage.get("total_tokens")]
    if details:
        parts.append("completion_tokens_details=%s" % json.dumps(details, ensure_ascii=False))
    return "，".join(str(p) for p in parts)


def diagnose_empty_response(resp_json):
    """content 为空时，拼出"为什么拿不到结果"的完整诊断。"""
    choice = (resp_json.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason")
    reasoning = message.get("reasoning_content") or ""
    usage = resp_json.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens")

    lines = [
        "未拿到分类结果。原因诊断：",
        "  - finish_reason = %r" % finish_reason,
        "  - usage：%s" % format_usage(usage),
    ]
    if reasoning_tokens is not None:
        lines.append("  - 其中思考(reasoning) token 占用：%s" % reasoning_tokens)
    if reasoning:
        preview = reasoning[:120] + ("……" if len(reasoning) > 120 else "")
        lines.append("  - 模型只输出了思考内容（reasoning_content 开头）：%s" % preview)
    else:
        lines.append("  - 响应中没有可用的 reasoning_content / content 文本。")

    if finish_reason == "length":
        lines.append(
            "  结论：kimi-k3 无法关闭思考（官方文档：K3 不支持 thinking 参数，始终推理），\n"
            "  且思考 token 计入 max_tokens 输出预算。在 64 token 上限内，思考过程先耗尽了\n"
            "  全部预算（completion_tokens 已到 %s），最终答案 content 一个 token 都没生成，\n"
            "  所以 finish_reason=length、content 为空。这不是脚本解析问题，是 64 token 的\n"
            "  硬上限与『必须思考的模型』在物理上不兼容。" % usage.get("completion_tokens", MAX_TOKENS)
        )
        lines.append(
            "  可选出路（都会突破本次 64 token 的约束，需要你决策）：\n"
            "    1) 把 MAX_TOKENS 提到几百以上（官方对思考模型工具场景的建议是 >=16000）；\n"
            "    2) 换成可关闭思考的模型（如 kimi-k2.6 传 thinking={\"type\":\"disabled\"}，\n"
            "       或其他非推理模型）再做三分类。"
        )
    return "\n".join(lines)


# ---------------------------- 主流程 ----------------------------

def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        fail("错误：未设置环境变量 %s。请先执行：export %s=<你的火山方舟 API Key>" % (API_KEY_ENV, API_KEY_ENV))

    # 第一次尝试：reasoning_effort="low" 是 kimi-k3 唯一能调低思考量的开关
    # （取值 low/high/max，默认 max；默认档位下 64 token 必然不够思考用）。
    attempts = [
        {"name": "reasoning_effort=low", "extra": {"reasoning_effort": "low"}},
    ]

    attempt_index = 0
    while attempt_index < len(attempts):
        attempt = attempts[attempt_index]
        attempt_index += 1
        print("第 %d 次调用：%s（max_tokens=%d，输出上限不变）……"
              % (attempt_index, attempt["name"], MAX_TOKENS))

        try:
            resp = call_model(api_key, attempt["extra"])
        except requests.exceptions.Timeout:
            fail("错误：请求超时（>%ds）。网络不通或服务端繁忙，请重试。" % TIMEOUT_SECONDS)
        except requests.exceptions.ConnectionError as exc:
            fail("错误：无法连接 %s（%s）。请检查网络/代理设置。" % (BASE_URL, exc))

        # HTTP 层错误：分类失败要给出可读的原因
        if resp.status_code == 400:
            body = resp.text
            # 若是 reasoning_effort 这个参数不被当前网关/模型接受，降级重试一次
            if "reasoning_effort" in body and attempt["extra"]:
                print("  网关拒绝了 reasoning_effort 参数，降级为默认参数重试……")
                attempts.append({"name": "默认参数（不带 reasoning_effort）", "extra": {}})
                continue
            fail("错误：请求参数被拒绝（HTTP 400）：%s" % body)
        if resp.status_code in (401, 403):
            fail("错误：API Key 无效或无权限（HTTP %d）：%s。请检查 %s 是否为有效的火山方舟 Key。"
                 % (resp.status_code, resp.text, API_KEY_ENV))
        if resp.status_code == 404:
            fail("错误：接口或模型不存在（HTTP 404）：%s。请核对模型 ID「%s」是否是 Agent Plan 支持的准确写法"
                 "（可用环境变量 ARK_MODEL 覆盖），以及 ARK_BASE_URL 是否正确。" % (resp.text, MODEL))
        if resp.status_code == 429:
            fail("错误：触发限流（HTTP 429）：%s。请稍后重试。" % resp.text)
        if resp.status_code >= 500:
            fail("错误：服务端错误（HTTP %d）：%s。请稍后重试。" % (resp.status_code, resp.text))
        if resp.status_code != 200:
            fail("错误：意外的 HTTP 状态码 %d：%s" % (resp.status_code, resp.text))

        try:
            resp_json = resp.json()
        except ValueError:
            fail("错误：响应不是合法 JSON（可能网关地址不对，返回了 HTML）：%.200s" % resp.text)

        choices = resp_json.get("choices") or []
        if not choices:
            fail("错误：响应中没有 choices：%s" % json.dumps(resp_json, ensure_ascii=False))

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        usage = resp_json.get("usage") or {}

        label = extract_label(content)
        if label is not None:
            # 成功：拿到确定的分类结果，且输出成本有据可查
            print("情感分类结果：%s" % label)
            print("（模型 %s，%s，token 用量：%s）"
                  % (MODEL, attempt["name"], format_usage(usage)))
            return

        # 没拿到有效结果：区分"完全为空"和"输出了解释性文字但不含有效标签"
        if not content.strip():
            fail(diagnose_empty_response(resp_json))
        else:
            fail("未拿到有效分类结果：模型输出里找不到唯一的「正面/负面/中性」标签。\n"
                 "  原始输出（%.200s）\n  finish_reason=%r，usage：%s"
                 % (content, choices[0].get("finish_reason"), format_usage(usage)))

    fail("错误：所有尝试方案均已用尽，仍未取得分类结果。")


if __name__ == "__main__":
    main()
