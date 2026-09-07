#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具。

调用智谱开放平台的 chat/completions 接口，挂 web_search 工具联网检索后，
回答写死的问题，并把接口真实返回的搜索来源（标题 + 可点击 URL）列在答案下面。

运行前提：
    export ZHIPUAI_API_KEY="你的 API Key"   # https://bigmodel.cn/usercenter/proj-mgmt/apikeys
    pip install requests                    # 仅依赖 requests

用法：
    python3 main.py
"""

import os
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
CHAT_URL = f"{API_BASE}/chat/completions"
MODEL = "glm-5.3"

# 写死的问题
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def ask_with_web_search(api_key: str, question: str) -> dict:
    """带联网搜索调用模型，返回原始响应 JSON。

    两个关键参数，缺一个都会让"展示真实来源"这个需求静默失效：
    - search_result=True：响应体顶层才会带 web_search 来源数组（默认 false 时
      搜索照常执行、回答照常生成，但响应里完全没有来源字段）；
    - require_search=True：强制先搜索再回答，避免模型凭训练记忆作答。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的联网问答助手。请只依据联网搜索到的信息回答，"
                    "在回答中标注关键事实的出处，不确定的内容要明确说明，不要编造。"
                ),
            },
            {"role": "user", "content": question},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",
                    "search_result": True,             # 让接口返回真实搜索来源
                    "require_search": True,            # 强制联网搜索后才回答
                    "search_recency_filter": "oneYear",  # 问题关注 2026 年新发布
                    "count": 10,
                },
            }
        ],
        "stream": False,
    }
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=180,
    )
    if not resp.ok:
        # 业务错误（如 1113 余额不足、1210 参数非法）写在响应体的 error 字段里
        raise RuntimeError(f"接口调用失败 HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def dedupe_sources(sources: list) -> list:
    """按链接去重，保持原顺序；无链接的条目保留不合并。"""
    seen = set()
    unique = []
    for item in sources:
        link = (item.get("link") or "").strip()
        key = link if link else f"_no_link_{len(unique)}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        return 1

    data = ask_with_web_search(api_key, QUESTION)

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"响应中没有 choices：{data}")
    answer = choices[0].get("message", {}).get("content") or "(模型没有返回内容)"

    print(f"问题：{QUESTION}\n")
    print("回答：")
    print(answer)

    # 来源只取响应顶层 web_search 数组——这是本次搜索接口真实返回的结果，
    # 不是模型生成的文本，链接可直接点击核对。
    sources = dedupe_sources(data.get("web_search") or [])
    print("\n" + "=" * 60)
    print("信息来源（接口本次真实返回的联网搜索结果）：")
    if not sources:
        print("（接口没有返回任何搜索来源，上面的回答缺乏可核对的出处）")
    for i, item in enumerate(sources, 1):
        title = (item.get("title") or "(无标题)").strip()
        link = (item.get("link") or "").strip()
        media = (item.get("media") or "").strip()
        date = (item.get("publish_date") or "").strip()
        meta = " / ".join(x for x in (media, date) if x)
        print(f"[{i}] {title}" + (f"（{meta}）" if meta else ""))
        print(f"    {link}" if link else "    (无链接)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
