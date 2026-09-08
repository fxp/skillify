#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具：调用智谱 GLM 模型 + 联网搜索回答一个写死的问题，
并把本次回答实际参考的信息来源（标题 + 可点击 URL）打印到 stdout。

来源取自响应体顶层的 web_search 数组——即接口真实返回的搜索引用，
不是模型凭印象生成的链接。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

# 联网搜索工具配置。两个容易踩的坑（官方文档没写清、HTTP 200 静默失效）：
# 1. search_engine 不能用 search_std / search_pro——它们返回的来源 link 恒为空字符串，
#    只有标题和摘要。要可点击的来源链接，必须选 search_pro_sogou / search_pro_quark /
#    search_pro_bing / search_pro_jina 之一。这里选 sogou，新闻资讯覆盖较好。
# 2. search_result 必须显式传 true，响应体顶层才会带 web_search 来源数组；
#    不传（默认 false）时搜索照常执行、答案照常生成，但响应里完全没有出处字段。
WEB_SEARCH_TOOL = {
    "type": "web_search",
    "web_search": {
        "enable": True,
        "search_engine": "search_pro_sogou",
        "search_result": True,              # 必须显式开启，否则响应中没有来源数组
        "count": 10,
        "search_recency_filter": "oneYear", # 只查一年内，聚焦 2026 年的新发布
        "content_size": "medium",
    },
}


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=你的Key")

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [WEB_SEARCH_TOOL],
        "tool_choice": "auto",
        "stream": False,
        # glm-5.3 的思考 token 也计入 max_tokens，预算给足，避免内容被思考吃光后截断
        "max_tokens": 16384,
    }

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        sys.exit(f"错误：请求失败：{exc}")

    try:
        body = resp.json()
    except ValueError:
        sys.exit(f"错误：HTTP {resp.status_code}，响应不是 JSON：{resp.text[:500]}")

    if not resp.ok or body.get("error"):
        err = body.get("error") or {}
        sys.exit(
            f"错误：HTTP {resp.status_code}，"
            f"code={err.get('code', 'N/A')}，message={err.get('message') or resp.text[:500]}"
        )

    choices = body.get("choices") or []
    if not choices:
        sys.exit(f"错误：响应中没有 choices：{body}")

    finish_reason = choices[0].get("finish_reason")
    answer = (choices[0].get("message") or {}).get("content") or ""
    answer = answer.strip()

    if not answer:
        # 空内容最常见的原因是 finish_reason=length：预算被思考 token 吃光后被截断
        sys.exit(
            f"错误：模型返回了空内容（finish_reason={finish_reason}）。"
            "若为 length，请调大 max_tokens 后重试。"
        )
    if finish_reason == "length":
        print(f"[警告] finish_reason=length，回答可能被截断。", file=sys.stderr)

    # 来源列表：只取接口真实返回的 web_search 数组，过滤掉 link 为空的条目并按 URL 去重
    sources = []
    seen_links = set()
    for item in body.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        title = (item.get("title") or "").strip() or "(无标题)"
        meta = "、".join(
            part for part in [(item.get("media") or "").strip(),
                              (item.get("publish_date") or "").strip()] if part
        )
        sources.append((title, link, meta))

    print(f"问题：{QUESTION}\n")
    print("回答：")
    print(answer)
    print()

    if sources:
        print(f"参考来源（接口 web_search 字段实际返回，共 {len(sources)} 条，可直接点击核对）：")
        for i, (title, link, meta) in enumerate(sources, 1):
            suffix = f"（{meta}）" if meta else ""
            print(f"  {i}. {title}{suffix}")
            print(f"     {link}")
    else:
        # 引擎返回了空链接或未返回来源时，绝不编造，明确告知
        print(
            "[注意] 本次接口没有返回任何带可点击链接的搜索来源"
            "（web_search 数组为空或 link 全为空串），无法提供核对链接。"
        )


if __name__ == "__main__":
    main()
