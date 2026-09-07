#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具。

问智谱 BigModel「2026 年智谱 BigModel 发布了哪些新模型」，
模型通过 web_search 工具联网检索后作答；
答案下方列出本次接口**真实返回**的搜索来源（标题 + 可点击 URL），
链接全部来自接口响应，绝不让模型凭印象编造。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

依赖：仅 requests。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 写死的问题
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型？请具体说明模型名称、定位和亮点。"

# 默认模型，可用环境变量 ZHIPUAI_MODEL 覆盖
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")

TIMEOUT_SECONDS = 120  # 联网搜索 + 生成可能较慢


def ask_with_web_search(api_key):
    """调用对话补全接口，开启 web_search 工具并要求返回搜索来源。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",  # 多引擎协作，来源质量更好
                    "search_result": True,          # 关键：让接口把真实搜索来源随响应返回
                    "count": 10,
                    "content_size": "high",
                },
            }
        ],
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        # 带出接口错误详情，方便排查（Key 无效、余额不足等）
        raise RuntimeError("接口返回 HTTP %d: %s" % (resp.status_code, resp.text))
    return resp.json()


def extract_sources(data):
    """从响应里提取接口真实返回的搜索来源（标题 + 链接）。

    当前文档：来源在响应顶层 `web_search` 数组；
    兼容旧结构：choices[0].message.tool_calls[].web_search.search_result。
    """
    items = []

    # 新结构：顶层 web_search 数组
    if isinstance(data.get("web_search"), list):
        items.extend(data["web_search"])

    # 旧结构：message.tool_calls 里携带
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        for tool_call in message.get("tool_calls") or []:
            web_search = tool_call.get("web_search") or {}
            if isinstance(web_search.get("search_result"), list):
                items.extend(web_search["search_result"])

    # 整理去重（按链接），只保留带有效链接的条目
    seen = set()
    sources = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = (item.get("link") or "").strip()
        if not link.startswith(("http://", "https://")) or link in seen:
            continue
        seen.add(link)
        title = (item.get("title") or "(无标题)").strip()
        media = (item.get("media") or "").strip()
        sources.append({"title": title, "link": link, "media": media})
    return sources


def main():
    # 保证中文在任何终端配置下都能正常输出
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    print("问题：%s" % QUESTION)
    print("模型：%s（web_search 联网搜索已开启）\n" % MODEL)
    print("正在联网检索并生成答案，请稍候…\n")

    try:
        data = ask_with_web_search(api_key)
    except requests.RequestException as exc:
        print("错误：请求失败：%s" % exc, file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 1

    choices = data.get("choices") or []
    answer = ""
    if choices:
        answer = (choices[0].get("message") or {}).get("content") or ""
    print(answer.strip() or "（模型没有返回文本内容）")

    sources = extract_sources(data)
    print("\n" + "─" * 60)
    if sources:
        print("参考来源（%d 条，均来自本次接口真实返回的搜索结果）：" % len(sources))
        for i, src in enumerate(sources, 1):
            suffix = "（%s）" % src["media"] if src["media"] else ""
            print("%d. %s%s" % (i, src["title"], suffix))
            print("   %s" % src["link"])
    else:
        print("注意：本次接口没有返回任何搜索来源，无法提供可核对的链接。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
