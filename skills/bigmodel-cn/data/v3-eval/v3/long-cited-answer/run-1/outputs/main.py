#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 AI 开放平台（bigmodel.cn）的联网搜索能力回答：
    2026 年中国新能源汽车出口的主要目的地国家有哪些？

硬性要求（任一不满足就明确报错退出，绝不输出半成品）：
  1. 答案完整：finish_reason 必须是 "stop"；返回 "length" 说明被截断，
     会先把 max_tokens 翻倍重试，重试用尽上限仍截断才报错；
  2. 至少 2 条可点击来源链接：取响应顶层 web_search 数组里 link 以 http
     开头的真实网址（按链接去重），不足 2 条视为失败。

运行方式：
    export ZHIPUAI_API_KEY=<你的智谱标准 API Key>
    python3 main.py

实现依据（bigmodel-cn 技能包用真实 API 实测的结论，勿凭印象改）：
  * chat/completions 挂 tools:[{"type":"web_search",...}] 时，必须显式传
    web_search.search_result=true——不传的话搜索照跑、答案照给，但响应里
    根本不会出现 web_search 来源数组（典型静默失效）；
  * 来源 link 是否非空完全取决于 search_engine：search_std / search_pro 恒为
    空串，只有 search_pro_bing / _jina / _quark / _sogou 带真实链接（前两个
    官方参数表未列出但实测可用）。因此按优先级逐个尝试，某个引擎链接不足
    就换下一个重跑，而不是把"没有链接"当成正常结果；
  * 思考 token 计入 max_tokens：finish_reason=="length" 是预算被思考吃光了，
    补救办法是翻倍 max_tokens 重试，不是把截断的答案交付出去；
  * 标准端点上 glm-5.3 传 thinking:{"type":"disabled"} 会报 1210（思考关不掉），
    所以这里不传 thinking，靠给足 max_tokens 保证完整性。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年中国新能源汽车出口的主要目的地国家有哪些？"

# 实测 link 非空的引擎，按优先级排列。
# 不要换成 search_std / search_pro：那两个引擎返回的来源 link 恒为空字符串。
SEARCH_ENGINES = ("search_pro_bing", "search_pro_quark", "search_pro_sogou", "search_pro_jina")

MIN_SOURCES = 2          # 至少要给出 2 条可点击来源
MAX_TOKENS_START = 8192  # 首次预算：思考 token 也计入 max_tokens，必须给足
MAX_TOKENS_CAP = 32768   # 截断重试时预算翻倍的上限
REQUEST_TIMEOUT = 180    # 联网搜索 + 长思考，单次调用可能较慢


def fail(msg):
    """明确报错并退出：宁可失败，也不给半截结果。"""
    print("[错误] " + msg, file=sys.stderr)
    sys.exit(1)


def post_json(api_key, payload):
    """发请求（瞬时网络错误重试 1 次）。HTTP / API 层失败抛 RuntimeError 并带上报错详情。"""
    last_exc = None
    resp = None
    for _ in range(2):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            break
        except requests.RequestException as exc:
            last_exc = exc
    if resp is None:
        raise RuntimeError("网络请求失败（已重试 1 次）：" + str(last_exc))

    if resp.status_code != 200:
        raise RuntimeError("HTTP %d：%s" % (resp.status_code, resp.text[:500]))

    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError("响应不是合法 JSON：" + resp.text[:500])

    # 平台业务错误放在 body["error"]（如 1210 参数错误、1113 余额/端点错误）
    if isinstance(body.get("error"), dict):
        err = body["error"]
        raise RuntimeError(
            "API 报错 code=%s message=%s" % (err.get("code"), err.get("message"))
        )
    if not body.get("choices"):
        raise RuntimeError("响应里没有 choices：" + str(body)[:500])
    return body


def build_payload(engine, max_tokens):
    """构造一次「联网搜索 + 回答」请求。"""
    return {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是严谨的行业研究助理，必须依据联网搜索到的最新资料作答。",
            },
            {
                "role": "user",
                "content": QUESTION + "\n\n"
                "请基于联网搜索结果回答：列出 2026 年中国新能源汽车出口的主要目的地国家，"
                "尽量按出口规模排序并附上能查到的数据（如出口量、同比增速）或趋势判断，"
                "最后作简要小结。回答必须完整成篇，不要中途截断。",
            },
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    "search_result": True,  # 关键：不显式传 true，响应就不带 web_search 来源数组
                    "search_recency_filter": "oneYear",
                },
            }
        ],
        "max_tokens": max_tokens,
        "stream": False,
        # 注意：这里刻意不传 thinking——标准端点 glm-5.3 传
        # thinking:{"type":"disabled"} 会报 1210，保持默认开启，用大 max_tokens 兜完整性。
    }


def collect_sources(body):
    """从响应顶层 web_search 数组提取可点击来源（link 以 http 开头），按链接去重。"""
    sources = []
    seen = set()
    for item in body.get("web_search") or []:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        sources.append(
            {
                "title": str(item.get("title") or "").strip() or "（无标题）",
                "media": str(item.get("media") or "").strip(),
                "publish_date": str(item.get("publish_date") or "").strip(),
                "link": link,
            }
        )
    return sources


def run_with_engine(api_key, engine):
    """用一个搜索引擎跑完整链路：被截断就把 max_tokens 翻倍重试。

    返回 dict：ok=True 时带 content / sources / model（服务端回显的模型名）；
    ok=False 时 error 里是这条链路失败的具体原因。
    """
    max_tokens = MAX_TOKENS_START
    while True:
        body = post_json(api_key, build_payload(engine, max_tokens))
        choice = body["choices"][0]
        finish_reason = choice.get("finish_reason")
        content = (choice.get("message") or {}).get("content") or ""
        echoed_model = str(body.get("model") or "")

        if finish_reason == "length":
            # 被截断：翻倍预算重试，绝不交付半截答案
            if max_tokens >= MAX_TOKENS_CAP:
                return {
                    "ok": False,
                    "error": "答案被截断（finish_reason=length），max_tokens 已加到 "
                             "%d 仍不完整" % max_tokens,
                }
            max_tokens = min(max_tokens * 2, MAX_TOKENS_CAP)
            print("[重试] %s 返回 finish_reason=length，max_tokens 翻倍到 %d 后重试"
                  % (engine, max_tokens), file=sys.stderr)
            continue

        if finish_reason != "stop":
            return {
                "ok": False,
                "error": "回答异常结束：finish_reason=%s（只有 stop 才算完整；"
                         "sensitive=内容拦截，network_error=推理异常）" % finish_reason,
            }
        if not content.strip():
            return {"ok": False, "error": "finish_reason=stop 但 content 为空串"}

        return {"ok": True, "content": content, "sources": collect_sources(body),
                "model": echoed_model}


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置。请先执行：export ZHIPUAI_API_KEY=<你的智谱 API Key>，"
             "再运行 python3 main.py。")

    failures = []
    for engine in SEARCH_ENGINES:
        try:
            result = run_with_engine(api_key, engine)
        except RuntimeError as exc:
            failures.append("%s：%s" % (engine, exc))
            continue

        if not result["ok"]:
            failures.append("%s：%s" % (engine, result["error"]))
            continue

        # 答案完整，但来源链接不足 → 换引擎重跑（不同引擎 link 是否为空表现不同）
        if len(result["sources"]) < MIN_SOURCES:
            failures.append(
                "%s：回答本身完整，但来源里 link 非空的可点击链接只有 %d 条（要求 >= %d），"
                "换下一个引擎重试" % (engine, len(result["sources"]), MIN_SOURCES)
            )
            continue

        # 服务端回显模型与请求不一致时提醒（同步端点正常不会换模型；换成了别家模型要警惕）
        echoed = result["model"]
        if echoed and not echoed.startswith(MODEL):
            print("[警告] 服务端实际返回模型为 %s（请求的是 %s），请核对计费与能力是否受影响"
                  % (echoed, MODEL), file=sys.stderr)

        print("=" * 64)
        print("问题：" + QUESTION)
        print("（模型 %s · 搜索引擎 %s · finish_reason=stop · 答案完整未截断）"
              % (echoed or MODEL, engine))
        print("=" * 64)
        print()
        print(result["content"].strip())
        print()
        print("=" * 64)
        print("来源链接（共 %d 条，供人工复核）：" % len(result["sources"]))
        for i, s in enumerate(result["sources"], 1):
            meta = "，".join(x for x in (s["media"], s["publish_date"]) if x)
            line = "%d. %s" % (i, s["title"])
            if meta:
                line += "（%s）" % meta
            print(line)
            print("   " + s["link"])
        return

    fail(
        "所有候选搜索引擎都没能同时满足「答案完整 + 至少 %d 条可点击来源链接」，逐项失败原因：\n  - %s\n"
        "排查建议：单项里若有 API 报错码，1113 多为 Key/端点不匹配（编程套餐 Key 打了标准端点），"
        "1210/1214 为参数或模型名问题；若各引擎都只报「链接不足」，说明当次搜索未返回非空 link，"
        "可稍后重跑。" % (MIN_SOURCES, "\n  - ".join(failures))
    )


if __name__ == "__main__":
    main()
