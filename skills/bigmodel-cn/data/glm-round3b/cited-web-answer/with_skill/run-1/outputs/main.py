#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具：调用智谱 GLM 模型 + 联网搜索回答问题，并打印本次回答实际参考的信息来源。

来源列表取自 chat/completions 响应体顶层的 `web_search` 数组（由平台搜索服务返回），
不是模型生成的文本，因此每条链接都真实可点击、可核对。

两个关键参数说明（缺一个都拿不到可点击来源）：
- tools[].web_search.search_result = True   # 不传则响应体里没有 web_search 来源数组
- search_engine = "search_pro_bing"          # search_std/search_pro 返回的 link 恒为空字符串

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

REQUEST_TIMEOUT = 300  # glm-5.3 强制思考 + 联网搜索，整体耗时可能较长
MAX_ATTEMPTS = 3       # 仅对 429/5xx 重试，4xx 配置类错误直接失败


def build_payload():
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 注意：search_std / search_pro 的来源 link 为空串，必须选下面这几个引擎
                    "search_engine": "search_pro_bing",
                    # 必须显式传 True，响应体顶层才会带 web_search 来源数组
                    "search_result": True,
                    "count": 10,
                    # 只问 2026 年的新模型，限定一年内，过滤往年旧闻
                    "search_recency_filter": "oneYear",
                    "content_size": "medium",
                },
            }
        ],
        "stream": False,
    }


def format_error(payload):
    """把响应体里的业务错误（{"error": {"code": ..., "message": ...}}）格式成一行。"""
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        return f"业务错误 {err.get('code')}: {err.get('message')}"
    return str(payload)[:500]


def chat_with_web_search(api_key):
    """发起带联网搜索的对话请求，带 429/5xx 指数退避重试，返回响应 JSON。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = build_payload()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            if attempt == MAX_ATTEMPTS:
                sys.exit(f"错误：请求智谱 API 失败：{exc}")
            wait = 2 ** attempt
            print(f"网络异常（{exc}），{wait}s 后重试（{attempt}/{MAX_ATTEMPTS}）…", flush=True)
            time.sleep(wait)
            continue

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.ok and "error" not in data:
            return data

        # 429 / 5xx 属于临时性错误，退避后重试；其余（401/403/400 等）重试无意义
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            wait = 2 ** attempt
            print(
                f"HTTP {resp.status_code}（{format_error(data)}），"
                f"{wait}s 后重试（{attempt}/{MAX_ATTEMPTS}）…",
                flush=True,
            )
            time.sleep(wait)
            continue

        sys.exit(f"错误：API 调用失败，HTTP {resp.status_code}，{format_error(data)}")


def print_answer(data):
    choices = data.get("choices") or []
    if not choices:
        sys.exit(f"错误：响应里没有 choices，原始返回：{str(data)[:500]}")

    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")

    if not answer:
        sys.exit(f"错误：模型没有返回回答内容（finish_reason={finish_reason}）")

    print("回答：")
    print(answer)
    if finish_reason not in (None, "stop"):
        print(f"\n（注意：finish_reason={finish_reason}，回答可能被截断或拦截）")


def print_sources(data):
    """打印接口真实返回的引用来源（响应顶层 web_search 数组），过滤空链接并按 URL 去重。"""
    raw_sources = data.get("web_search") or []

    print("\n" + "=" * 60)
    print("参考来源（来自接口本次返回的 web_search 字段，非模型生成）：")

    sources, seen_links = [], set()
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        link = (item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append(item)

    if not sources:
        if raw_sources:
            print("  本次接口返回的来源均未携带链接（link 为空），无法提供可点击的 URL。")
            print("  可尝试把脚本里的 search_engine 换成 search_pro_bing / search_pro_quark /")
            print("  search_pro_jina / search_pro_sogou 之一再运行。")
        else:
            print("  接口本次未返回任何来源信息。")
        return

    for idx, item in enumerate(sources, 1):
        title = (item.get("title") or "").strip() or "（无标题）"
        link = (item.get("link") or "").strip()
        media = (item.get("media") or "").strip()
        publish_date = (item.get("publish_date") or "").strip()
        meta = " / ".join(x for x in (media, publish_date) if x)
        print(f"{idx}. {title}")
        if meta:
            print(f"   {meta}")
        print(f"   {link}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行：export ZHIPUAI_API_KEY=你的Key")

    print(f"问题：{QUESTION}")
    print(f"（正在调用 {MODEL} 并联网搜索，请稍候…）\n", flush=True)

    data = chat_with_web_search(api_key)
    print_answer(data)
    print_sources(data)


if __name__ == "__main__":
    main()
