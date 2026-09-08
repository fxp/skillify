#!/usr/bin/env python3
"""联网问答小工具：调用智谱 GLM（带联网搜索）回答一个写死的问题，
并打印本次回答实际参考的信息来源（标题 + 可点击 URL）。

来源列表直接取自 chat/completions 响应顶层的 web_search 数组
（接口真实返回的检索结果），不经过模型生成，因此链接可逐条点开核对。

用法：
    export ZHIPUAI_API_KEY="你的标准 API Key"
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY，"
            "请先 export ZHIPUAI_API_KEY=<你的标准 API Key> 再运行。",
            file=sys.stderr,
        )
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": QUESTION + "\n请基于联网搜索到的最新资料回答，注意区分官方发布与传闻。",
            }
        ],
        # glm-5.3 在标准端点强制开启深度思考，且思考 token 计入 max_tokens：
        # 预算给足，避免 finish_reason=length 导致正文为空。
        "max_tokens": 8192,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 关键：search_std / search_pro 返回的来源 link 恒为空字符串，
                    # 只有 search_pro_bing / _sogou / _quark / _jina 带真实可点击链接。
                    "search_engine": "search_pro_bing",
                    # 关键：不显式传 true 时搜索照常执行，但响应体里
                    # 不会出现顶层 web_search 来源数组，无法展示出处。
                    "search_result": True,
                    "search_recency_filter": "oneYear",
                },
            }
        ],
        "stream": False,
    }

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
    except requests.RequestException as exc:
        print(f"错误：请求失败：{exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(
            f"错误：API 返回 HTTP {resp.status_code}：{resp.text}",
            file=sys.stderr,
        )
        return 1

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        print(f"错误：响应中没有 choices：{data}", file=sys.stderr)
        return 1

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content") or ""

    print(f"问题：{QUESTION}")
    print("=" * 60)
    print(content)

    if finish_reason != "stop":
        print(
            f"警告：finish_reason={finish_reason!r}（正文可能被截断）",
            file=sys.stderr,
        )

    # 来源列表只取接口返回的 web_search 数组，模型正文的自由发挥一概不采信
    sources = data.get("web_search") or []
    seen_links = set()
    shown = []
    for item in sources:
        link = (item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        shown.append(item)

    print("=" * 60)
    print(f"参考来源（共 {len(shown)} 条，由接口真实返回，可点击核对）：")
    if not shown:
        if sources:
            print(
                "警告：接口返回了 "
                f"{len(sources)} 条来源，但 link 全为空——"
                "请检查 search_engine 是否误用了 search_std/search_pro。",
                file=sys.stderr,
            )
        else:
            print("（本次响应未返回带链接的搜索来源。）", file=sys.stderr)
        return 0

    for idx, item in enumerate(shown, 1):
        title = (item.get("title") or "(无标题)").strip()
        media = (item.get("media") or "").strip()
        publish_date = (item.get("publish_date") or "").strip()
        meta = " / ".join(part for part in (media, publish_date) if part)
        suffix = f"（{meta}）" if meta else ""
        print(f"{idx}. {title}{suffix}")
        print(f"   {item['link'].strip()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
