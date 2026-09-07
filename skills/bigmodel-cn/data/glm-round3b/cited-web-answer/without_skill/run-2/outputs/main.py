#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网问答小工具

带着内置问题调用智谱 BigModel 对话补全接口（开启 web_search 联网搜索），
先打印模型回答，再列出本次回答实际参考的信息来源（标题 + 可点击 URL）。

来源说明：链接只从接口响应的 web_search / search_result 字段中读取——即接口
真实返回的检索结果，绝不使用模型凭印象生成的链接；若接口本次没有返回任何
来源，会明确提示而不是编造。

运行前设置环境变量：
    export ZHIPUAI_API_KEY="你的 API Key"
然后执行：
    python3 main.py
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 支持联网搜索工具的对话模型
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
TIMEOUT = 180  # 联网搜索 + 生成可能较慢，放宽超时


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=你的Key")
    return key


def ask_with_web_search(question):
    """调用对话补全接口：开启联网搜索，并要求接口返回搜索来源。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",  # 必填：搜索引擎编码
                    "search_result": True,  # 关键：要求接口在响应中返回真实搜索来源
                },
            }
        ],
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + get_api_key(),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )
    try:
        data = resp.json()
    except ValueError:
        sys.exit("错误：接口返回非 JSON 内容（HTTP %s）：%s" % (resp.status_code, resp.text[:500]))
    if resp.status_code != 200 or data.get("error"):
        sys.exit("错误：接口调用失败（HTTP %s）：%s" % (resp.status_code, json.dumps(data, ensure_ascii=False)))
    return data


def make_source(item):
    return {
        "refer": str(item.get("refer") or "").strip(),
        "title": str(item.get("title") or "(未提供标题)").strip(),
        "link": str(item.get("link") or "").strip(),
        "meta": " / ".join(str(x) for x in (item.get("media"), item.get("publish_date")) if x),
    }


def extract_sources(data):
    """
    只从接口响应结构中提取搜索来源（不经过模型正文），按 link 去重。

    兼容两种返回位置：
      1) 顶层 web_search 数组（search_result=true 时返回，当前主要格式）
      2) choices[0].message.tool_calls[*].search_result（旧版返回格式）
    """
    raw_items = []

    top = data.get("web_search")
    if isinstance(top, list):
        raw_items.extend(x for x in top if isinstance(x, dict))

    if not raw_items:
        for choice in data.get("choices") or []:
            for call in (choice.get("message") or {}).get("tool_calls") or []:
                items = call.get("search_result")
                if isinstance(items, list):
                    raw_items.extend(x for x in items if isinstance(x, dict))

    sources, seen = [], set()
    for item in raw_items:
        src = make_source(item)
        if src["link"] and src["link"] not in seen:
            seen.add(src["link"])
            sources.append(src)
    return sources


def main():
    print("问题：%s" % QUESTION)
    print("模型：%s（联网搜索：search_pro）" % MODEL)

    data = ask_with_web_search(QUESTION)

    choices = data.get("choices") or []
    answer = (choices[0].get("message") or {}).get("content") if choices else ""
    if not answer:
        sys.exit("错误：接口未返回回答内容：%s" % json.dumps(data, ensure_ascii=False)[:1000])

    print("\n===== 回答 =====")
    print(answer.strip())

    sources = extract_sources(data)
    print("\n===== 参考来源（由接口 web_search 字段真实返回，可点击核对）=====")
    if not sources:
        print("（本次接口未返回任何搜索来源，因此不展示链接——不使用模型凭印象生成的链接）")
        return
    for i, src in enumerate(sources, 1):
        tag = " [角标 %s]" % src["refer"] if src["refer"] else ""
        print("%d.%s %s" % (i, tag, src["title"]))
        print("   %s" % src["link"])
        if src["meta"]:
            print("   (%s)" % src["meta"])


if __name__ == "__main__":
    main()
