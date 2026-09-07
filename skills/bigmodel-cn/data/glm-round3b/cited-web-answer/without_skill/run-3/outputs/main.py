# -*- coding: utf-8 -*-
"""联网问答小工具。

调用智谱 BigModel 的 chat/completions 接口（内置 web_search 联网搜索工具）
回答一个写死的问题，把答案打印到 stdout，并在答案下方列出本次回答
实际参考的信息来源（标题 + 可点击 URL）。

来源全部提取自接口响应本身——新版 schema 的响应顶层 ``web_search`` 数组，
或旧版 ``choices[0].message.tool_calls`` 中 web_search 条目的
``search_result``——而不是模型生成的文本，因此链接可点开核对。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 当前旗舰对话模型，支持内置 web_search 工具
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def extract_sources(data):
    """从 chat/completions 响应中提取联网搜索真实返回的来源。

    兼容两种返回位置（官方文档不同版本口径不一，两处都查）：
    1. 响应顶层 ``web_search`` 数组（API 参考 ChatCompletionResponse schema）；
    2. ``choices[*].message.tool_calls`` 中 type == "web_search" 条目的
       ``search_result`` 数组（GLM-4 时代的行为）。

    每条结果取 title/link 字段，按 link 去重并保持原始顺序。
    """
    raw_items = []

    top = data.get("web_search")
    if isinstance(top, list):
        raw_items.extend(top)

    for choice in data.get("choices") or []:
        message = (choice or {}).get("message") or {}
        for tool_call in message.get("tool_calls") or []:
            if isinstance(tool_call, dict) and tool_call.get("type") == "web_search":
                raw_items.extend(tool_call.get("search_result") or [])

    sources, seen_links = [], set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        if title and link and link not in seen_links:
            seen_links.add(link)
            sources.append((title, link))
    return sources


def fetch_answer(api_key):
    """调用带联网搜索的对话接口，返回 (回答文本, 来源列表)。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",  # 搜索引擎，可选 search_std/search_pro 等
                    "search_result": True,  # 关键：要求接口把真实搜索结果一并返回
                },
            }
        ],
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    if resp.status_code != 200:
        sys.exit("接口返回 HTTP %s：%s" % (resp.status_code, resp.text))
    try:
        data = resp.json()
    except ValueError:
        sys.exit("接口返回的不是合法 JSON：%s" % resp.text[:500])
    if data.get("error"):
        sys.exit("接口返回错误：%s" % data["error"])

    choices = data.get("choices") or []
    if not choices:
        sys.exit("接口未返回 choices：%s" % data)
    answer = (choices[0].get("message") or {}).get("content") or ""
    return answer, extract_sources(data)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    answer, sources = fetch_answer(api_key)

    print("问题：%s\n" % QUESTION)
    print(answer.strip() or "（接口未返回回答文本）")

    print("\n参考来源（接口联网搜索真实返回）：")
    if sources:
        for index, (title, link) in enumerate(sources, 1):
            print("%d. %s" % (index, title))
            print("   %s" % link)  # URL 单独一行，终端里可直接点击
    else:
        print("（本次接口未返回任何搜索来源）")


if __name__ == "__main__":
    main()
