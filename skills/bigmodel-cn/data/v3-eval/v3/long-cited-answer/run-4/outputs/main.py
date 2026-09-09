#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱开放平台(bigmodel.cn)GLM 的联网搜索能力回答:
    2026 年中国新能源汽车出口的主要目的地国家有哪些?

硬性要求(任一不满足则显式报错退出,绝不输出半截结果):
  1. 答案完整 —— finish_reason 必须是 "stop"。若因 max_tokens 不足被截断
     (finish_reason == "length",GLM 的思考 token 也计入该预算),自动翻倍
     预算重试,而不是把半截答案交出去。
  2. 至少 2 条以 http 开头的真实来源链接 —— 只使用实测会返回非空 link 的
     搜索引擎(search_std / search_pro 的 link 恒为空字符串),且必须显式传
     web_search.search_result = true,否则响应里根本没有 web_search 来源数组
     (搜索照跑、答案照给,只是没出处)。

运行方式:
    ZHIPUAI_API_KEY=<你的Key> python3 main.py
依赖: 仅 requests
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
SEARCH_QUERY = "2026年中国新能源汽车出口主要目的地国家"  # web_search.search_query 限长 70 字
QUESTION = (
    "2026 年中国新能源汽车出口的主要目的地国家有哪些?"
    "请基于联网搜索到的最新资料给出完整、结构化的回答:"
    "逐个列出主要目的地国家(或地区),并简述各市场的规模与特点;"
    "答案必须完整,不得中途省略或停笔。"
)

# 实测对照(references/tools.md):search_std / search_pro 返回的来源 link 恒为
# 空字符串,只有下列引擎带真实可点击链接。按优先级轮换,某个引擎链接不足就换下一个。
# 注:search_pro_bing / search_pro_jina 未列入官方参数表但实测可用;
#     search_pro_sogou / search_pro_quark 是官方文档明确支持的。
SEARCH_ENGINES = ["search_pro_bing", "search_pro_sogou", "search_pro_quark", "search_pro_jina"]
MIN_LINKS = 2
# 思考(thinking)token 计入 max_tokens,预算不足会 finish_reason=length、答案被截断。
# 起步给足,截断则沿阶梯翻倍重试,而不是报错退出。
MAX_TOKENS_LADDER = [8192, 16384, 32768]
HTTP_TIMEOUT = 300  # 联网搜索 + 深度思考 + 长文生成整体耗时较长,超时给足


class ApiError(RuntimeError):
    """单次 API 调用失败(网络/HTTP/平台错误体),可换引擎或预算重试。"""


def die(msg):
    print(f"[失败] {msg}", file=sys.stderr)
    sys.exit(1)


def load_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die(
            "环境变量 ZHIPUAI_API_KEY 未设置或为空。"
            "请先执行:export ZHIPUAI_API_KEY=<你的智谱开放平台标准 API Key> 再运行本脚本。"
        )
    return key


def call_chat(api_key, engine, max_tokens):
    """发起一次带联网搜索工具的对话补全,返回解析后的响应 dict。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    "search_query": SEARCH_QUERY,  # 显式给定查询,强制触发搜索而非依赖模型自行判断
                    "search_result": True,  # 不显式传 true,响应顶层不会带 web_search 来源数组
                    "search_recency_filter": "oneYear",
                },
            }
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=HTTP_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise ApiError(f"网络/传输层错误:{exc}") from exc

    try:
        body = resp.json()
    except ValueError:
        raise ApiError(f"HTTP {resp.status_code},响应不是 JSON:{resp.text[:200]!r}")

    if resp.status_code != 200:
        err = body.get("error") or {}
        code, message = err.get("code"), err.get("message")
        hint = ""
        if str(code) == "1113":
            # 1113 常见成因之一是拿 GLM Coding Plan(编程套餐)Key 打标准端点,
            # 套餐 Key 调不了联网搜索,应换标准 API Key,而不是去充值。
            hint = "(提示:若你用的是编程套餐 Key,它不支持标准端点的联网搜索,请改用标准 API Key)"
        raise ApiError(f"HTTP {resp.status_code},错误码 {code},信息 {message}{hint}")
    if body.get("error"):  # 个别能力 HTTP 200 仍带 error 体,不能只看状态码
        raise ApiError(f"HTTP 200 但响应体含 error:{body['error']}")
    if not body.get("choices"):
        raise ApiError(f"响应缺少 choices 字段:{str(body)[:200]}")
    return body


def model_echo_ok(returned):
    """回显 model 与请求不一致时:仅版本号后缀差异(如 glm-5.3-260428)可接受;
    换成完全不同的模型意味着计费系数和能力都变了,本次结果不可信。"""
    return not returned or returned.startswith("glm-5.3")


def extract(body):
    """取出 (答案正文, finish_reason, 去重后的可用来源列表)。

    来源只保留 link 以 http 开头的条目(某些引擎 link 为空串,不可点击、无法复核)。
    """
    choices = body.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = message.get("content") or ""
    finish_reason = choice.get("finish_reason")

    sources, seen = [], set()
    for item in body.get("web_search") or []:
        link = str(item.get("link") or "").strip()
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        sources.append(
            {
                "title": str(item.get("title") or "").strip() or "(无标题)",
                "link": link,
                "media": str(item.get("media") or "").strip(),
                "date": str(item.get("publish_date") or "").strip(),
            }
        )
    return content, finish_reason, sources


def report(content, sources, engine, model_echo, finish_reason):
    print("=" * 14 + " 答案(已确认完整,可直接粘贴) " + "=" * 14)
    print(content.strip())
    print()
    print("=" * 14 + f" 来源链接(共 {len(sources)} 条,供人工复核) " + "=" * 14)
    for i, s in enumerate(sources, 1):
        meta = ", ".join(x for x in (s["media"], s["date"]) if x)
        print(f"[{i}] {s['title']}" + (f"({meta})" if meta else ""))
        print(f"    {s['link']}")
    print()
    print(
        f"(模型 {MODEL},响应回显 {model_echo or '未回显'};"
        f"搜索引擎 {engine};finish_reason={finish_reason})"
    )


def main():
    api_key = load_api_key()
    problems = []  # 如实记录每次尝试失败的原因,全败时逐条汇报,不糊弄

    for engine in SEARCH_ENGINES:
        for max_tokens in MAX_TOKENS_LADDER:
            label = f"引擎 {engine} / max_tokens {max_tokens}"
            print(f"[{label}] 请求中……", file=sys.stderr)
            try:
                body = call_chat(api_key, engine, max_tokens)
            except ApiError as exc:
                problems.append(f"{label}:调用失败,原因 → {exc}")
                break  # 传输/参数层错误,加大预算无济于事,直接换引擎

            model_echo = str(body.get("model") or "")
            if not model_echo_ok(model_echo):
                problems.append(
                    f"{label}:响应回显模型为 {model_echo},与请求的 {MODEL} 不是同一模型"
                    "(计费系数与能力可能已变),弃用本次结果,换引擎重试"
                )
                break

            content, finish_reason, sources = extract(body)
            if finish_reason == "length":
                # 答案被截断:翻倍预算在同一引擎上重试,绝不输出半截答案
                problems.append(f"{label}:答案被截断(finish_reason=length),加大 max_tokens 重试")
                continue
            if finish_reason != "stop" or not content.strip():
                # sensitive / network_error / model_context_window_exceeded 或空正文
                problems.append(
                    f"{label}:答案不完整或异常(finish_reason={finish_reason!r},"
                    f"正文 {len(content.strip())} 字),换引擎重试"
                )
                break
            if len(sources) < MIN_LINKS:
                # 答案虽完整,但没有足够可点击来源 → 不达标,换引擎(加预算不会多出链接)
                problems.append(
                    f"{label}:答案完整但仅有 {len(sources)} 条可点击来源链接"
                    f"(要求 ≥{MIN_LINKS},该引擎可能未返回非空 link),换引擎重试"
                )
                break

            # 两项硬性要求均满足,输出最终结果
            report(content, sources, engine, model_echo, finish_reason)
            return 0

    die(
        "未能产出满足要求的结果(答案完整 且 ≥"
        f"{MIN_LINKS} 条可点击来源链接),为避免给出半截/无出处答案,本脚本不输出任何结果。"
        "各次尝试的具体失败原因如下:\n  - " + "\n  - ".join(problems)
    )


if __name__ == "__main__":
    sys.exit(main())
