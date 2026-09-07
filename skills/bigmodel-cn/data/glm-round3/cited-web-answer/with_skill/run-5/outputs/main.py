#!/usr/bin/env python3
"""联网问答小工具：调用智谱开放平台 GLM 模型（带联网搜索）回答写死的问题，
并把本次回答实际参考的信息来源（标题 + URL）打印到 stdout。

来源说明：调用 chat/completions 时给 tools 挂上 web_search 工具，并且必须
显式传 web_search.search_result=true——这样响应体顶层才会带 web_search
引用数组（title/link/media/publish_date/...）。下面打印的每条来源都取自
该数组，绝不让模型自己编链接。

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

# 联网搜索工具定义。
# - search_engine 显式指定，不依赖未文档化的默认值
# - search_result 必须显式传 true：否则搜索照常执行，但响应体里没有
#   web_search 引用数组，"列出真实来源"会静默失效
WEB_SEARCH_TOOL = {
    "type": "web_search",
    "web_search": {
        "enable": True,
        "search_engine": "search_pro",
        "search_result": True,
        "count": 10,
    },
}


def ask_with_web_search(api_key: str, question: str) -> dict:
    """调用带联网搜索的对话补全，返回完整响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的联网问答助手。请基于联网搜索到的资料回答，"
                    "不要编造不存在的信息。"
                ),
            },
            {"role": "user", "content": question},
        ],
        "tools": [WEB_SEARCH_TOOL],
        "tool_choice": "auto",
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(10, 180),  # 联网检索 + 思考可能较慢，读超时给足
    )
    if not resp.ok:
        # 带出平台错误体（如 1113 余额不足、1210 参数非法），方便排查
        raise RuntimeError(f"API 请求失败 HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def format_source(index: int, source: dict) -> str:
    """把一条引用来源格式化为一行：序号. 标题（媒体，日期） URL"""
    bits = []
    media = (source.get("media") or "").strip()
    date = (source.get("publish_date") or "").strip()
    if media:
        bits.append(media)
    if date:
        bits.append(date)
    meta = f"（{'，'.join(bits)}）" if bits else ""
    return f"{index}. {source.get('title') or '（无标题）'}{meta}\n   {source.get('link') or '（无链接）'}"


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export 再运行。", file=sys.stderr)
        return 1

    data = ask_with_web_search(api_key, QUESTION)

    choices = data.get("choices") or []
    if not choices:
        print(f"错误：响应中没有 choices：{data}", file=sys.stderr)
        return 1

    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()

    finish_reason = choices[0].get("finish_reason")
    if finish_reason and finish_reason != "stop":
        print(f"提示：finish_reason={finish_reason}（回答可能被截断或拦截）", file=sys.stderr)

    print(f"问题：{QUESTION}\n")
    print("答案")
    print("-" * 60)
    print(answer or "（模型没有返回内容）")

    # 参考来源：只取响应体顶层 web_search 数组里的真实返回，按 link 去重保序
    sources = []
    seen_links = set()
    for item in data.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if link and link in seen_links:
            continue
        if link:
            seen_links.add(link)
        sources.append(item)

    print()
    print("参考来源（接口真实返回，可直接点击核对）")
    print("-" * 60)
    if not sources:
        print("（本次响应未返回 web_search 引用数组，无来源可列——"
              "宁可空缺也不编造链接）")
    else:
        for i, source in enumerate(sources, 1):
            print(format_source(i, source))

    return 0


if __name__ == "__main__":
    sys.exit(main())
