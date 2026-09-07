#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具：调用智谱 GLM 的 web_search 联网搜索回答一个写死的问题，
并在答案下方列出本次回答实际参考的信息来源（标题 + 可点击 URL）。

来源列表直接取自接口真实返回的搜索结果字段，不做任何拼接或凭空生成。

用法：
    export ZHIPUAI_API_KEY="你的 API Key"
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")  # 支持 web_search 工具的模型
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
TIMEOUT = 120  # 联网搜索可能较慢，放宽超时


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",  # 必填：search_std / search_pro / ...
                    "search_result": True,  # 关键：要求接口返回搜索来源详情
                    "count": 10,
                    "search_recency_filter": "noLimit",
                },
            }
        ],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        print(f"错误：请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(
            f"错误：接口返回 HTTP {resp.status_code}：{resp.text[:500]}",
            file=sys.stderr,
        )
        return 1

    data = resp.json()

    # 取回答正文
    answer = ""
    try:
        answer = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        pass
    if not answer:
        print(f"错误：接口未返回回答内容：{data}", file=sys.stderr)
        return 1

    print(answer)
    print()

    # 取接口真实返回的搜索来源。
    # 官方 schema 里来源在响应顶层 "web_search" 数组；部分版本也会放在
    # choices[0].message.web_search，两处都检查，取先命中的那个。
    sources = data.get("web_search")
    if not sources:
        try:
            sources = data["choices"][0]["message"].get("web_search") or []
        except (KeyError, IndexError, TypeError):
            sources = []

    print("=" * 60)
    print("参考来源（来自接口真实返回的联网搜索结果）：")
    print("=" * 60)
    if not sources:
        print("（接口本次未返回任何搜索来源，请检查 search_result 是否生效）")
        return 1

    for i, item in enumerate(sources, 1):
        title = (item.get("title") or "(无标题)").strip()
        link = (item.get("link") or "").strip()
        media = (item.get("media") or "").strip()
        publish_date = (item.get("publish_date") or "").strip()
        refer = str(item.get("refer") or i)  # 正文中的角标序号，没有则用序号
        meta = " / ".join(x for x in (media, publish_date) if x)
        print(f"[{refer}] {title}" + (f"（{meta}）" if meta else ""))
        print(f"    {link}" if link else "    (无链接)")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
