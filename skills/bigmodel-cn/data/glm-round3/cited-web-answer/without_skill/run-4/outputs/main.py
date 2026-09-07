#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网问答小工具。

向智谱 BigModel 的对话补全接口发起一次带联网搜索（web_search 工具）的提问，
把模型答案打印到 stdout，并在答案下方列出本次回答实际参考的信息来源。

来源不是模型自己凭印象写的，而是直接取自接口响应中真实返回的顶层
web_search 数组（每项含 title / link 等字段），每条都给出可点击的 URL，
便于人工核对。

运行方式：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

依赖：仅 requests。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 默认模型，可用环境变量 ZHIPUAI_MODEL 覆盖
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3")
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
REQUEST_TIMEOUT = 120  # 联网搜索较慢，超时给足


def die(msg):
    print("错误：%s" % msg, file=sys.stderr)
    sys.exit(1)


def ask_with_web_search(api_key):
    """调用对话补全接口（启用联网搜索），返回解析后的响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,  # 启用联网搜索
                    "search_engine": "search_pro",
                    "search_result": True,  # 关键：要求接口返回搜索来源明细
                },
            }
        ],
        "tool_choice": "auto",
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        die("请求智谱接口失败：%s" % exc)

    try:
        data = resp.json()
    except ValueError:
        die("接口返回了非 JSON 内容（HTTP %s）：%s" % (resp.status_code, resp.text[:300]))

    if resp.status_code != 200:
        # 智谱错误格式一般为 {"error": {"code": "...", "message": "..."}}
        err = data.get("error") or {}
        detail = err.get("message") or json.dumps(data, ensure_ascii=False)
        die("接口返回错误（HTTP %s）：%s" % (resp.status_code, detail))

    return data


def extract_answer(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def extract_sources(data):
    """从响应顶层的 web_search 数组提取来源：保持接口返回顺序，按 link 去重。"""
    seen_links = set()
    sources = []
    for item in data.get("web_search") or []:
        if not isinstance(item, dict):
            continue
        link = (item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append(item)
    return sources


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")

    data = ask_with_web_search(api_key)

    answer = extract_answer(data)
    if not answer:
        die(
            "接口没有返回答案内容，原始响应片段：%s"
            % json.dumps(data, ensure_ascii=False)[:500]
        )

    print("问题：%s" % QUESTION)
    print()
    print("答案：")
    print(answer)

    sources = extract_sources(data)
    print()
    print("=" * 60)
    print("参考来源（共 %d 条，均取自接口真实返回的 web_search 字段）：" % len(sources))
    if not sources:
        print("（本次接口未返回任何搜索来源）")
    for idx, item in enumerate(sources, 1):
        title = (item.get("title") or "（无标题）").strip()
        link = (item.get("link") or "").strip()
        media = (item.get("media") or "").strip()
        publish_date = (item.get("publish_date") or "").strip()
        meta_parts = [p for p in (media, publish_date) if p]
        meta = "（%s）" % " · ".join(meta_parts) if meta_parts else ""
        print("%d. %s%s" % (idx, title, meta))
        print("   %s" % link)


if __name__ == "__main__":
    main()
