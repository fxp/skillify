#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具（智谱 BigModel）。

脚本里写死一个问题，调用智谱 chat/completions 接口并附带 web_search 联网搜索工具，
把答案和本次回答实际参考的信息来源（标题 + 可点击 URL）打印到 stdout。

来源取自接口响应体顶层的 web_search 数组（每条含 title/link/media/publish_date），
即搜索工具真实返回的引用，不是模型凭印象生成的链接。

运行方式：
    ZHIPUAI_API_KEY=你的Key python3 main.py
"""

import os
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api"
CHAT_URL = f"{API_BASE}/paas/v4/chat/completions"
MODEL = "glm-5.3"

QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

# 搜索引擎必须选会返回真实链接的那几个：
# search_std / search_pro 返回的来源 link 恒为空字符串（实测），没法点击核对；
# search_pro_quark 是官方文档正式列出的引擎，实测每条来源都带可点击的 link。
SEARCH_ENGINE = "search_pro_quark"


def ask_with_web_search(question: str) -> dict:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY，例如：ZHIPUAI_API_KEY=xxx python3 main.py")

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": SEARCH_ENGINE,
                    # 必须显式传 true：不传时搜索照常执行、答案照常生成，
                    # 但响应体顶层不会带 web_search 来源数组，引用列表会静默拿不到。
                    "search_result": True,
                    "count": 10,
                    "content_size": "high",
                },
            }
        ],
        # 事实型检索问答，用最低推理强度换取更快的响应（glm-5.3 仅支持 max/high/low）
        "reasoning_effort": "low",
    }

    try:
        resp = requests.post(
            CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,  # 联网搜索 + 生成，整体耗时较长，放宽超时
        )
    except requests.RequestException as exc:
        sys.exit(f"错误：请求失败：{exc}")

    if resp.status_code != 200:
        sys.exit(f"错误：HTTP {resp.status_code}：{resp.text}")

    data = resp.json()
    if data.get("error"):
        sys.exit(f"错误：接口返回业务错误：{data['error']}")
    return data


def main() -> None:
    data = ask_with_web_search(QUESTION)

    choices = data.get("choices") or []
    if not choices:
        sys.exit(f"错误：响应中没有 choices：{data}")

    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")

    print(f"问题：{QUESTION}\n")
    print("回答：")
    print(answer or "（模型没有返回内容）")
    if finish_reason and finish_reason != "stop":
        print(f"\n[提示] finish_reason={finish_reason}")

    # 只展示接口真实返回的来源；link 为空的条目无法点击核对，过滤掉
    sources = [s for s in (data.get("web_search") or []) if isinstance(s, dict)]
    cited = [s for s in sources if (s.get("link") or "").strip()]

    print("\n" + "=" * 64)
    print(f"参考来源（{len(cited)} 条，均取自本次响应的 web_search 字段，可点击核对）：")
    if not cited:
        print("（本次响应没有返回可点击的来源链接）")
        return
    for i, s in enumerate(cited, 1):
        title = (s.get("title") or "（无标题）").strip()
        link = s["link"].strip()
        media = (s.get("media") or "").strip()
        date = (s.get("publish_date") or "").strip()
        meta = "，".join(x for x in (media, date) if x)
        print(f"  {i}. {title}")
        if meta:
            print(f"     {meta}")
        print(f"     {link}")


if __name__ == "__main__":
    main()
