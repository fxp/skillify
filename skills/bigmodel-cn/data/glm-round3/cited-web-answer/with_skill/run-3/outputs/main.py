#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具。

写死一个问题，调用智谱（bigmodel.cn）chat/completions 并开启联网搜索工具，
把答案和「本次回答接口真实返回的参考来源」一起打印到 stdout。

关键点：来源列表取自响应体顶层的 web_search 数组（每条含 title/link 等），
该数组只有在请求里显式传 web_search.search_result=true 时才会返回（默认 false：
搜索照常执行、答案照常生成，但响应里不带来源，代码读到的永远是空）。
因此下面的来源 100% 来自接口返回，不是模型凭印象编的链接。

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
TIMEOUT = (10, 180)  # (连接超时, 读取超时)；联网搜索 + 生成可能较慢，读取放宽


def build_payload(question: str) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的联网问答助手。请仅依据联网搜索到的事实回答，"
                "条理清晰；不确定的信息要明确说明，不要编造。",
            },
            {"role": "user", "content": question},
        ],
        # 联网搜索工具（平台侧自动执行检索并把结果喂给模型，不会走 tool_calls）
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",        # 多引擎协同，召回率更高
                    "search_result": True,                # 必须：true 才会在响应顶层返回 web_search 来源数组
                    "search_recency_filter": "oneYear",   # 问题关注 2026 年动态，限定一年内
                    "count": 10,
                    "content_size": "high",               # 给模型更详细的摘要，答案更具体
                },
            }
        ],
        # glm-5.3 在标准端点强制开启思考（传 disabled 会报 1210），
        # low 档实测接近不思考：事实型问答足够用，且明显更快
        "reasoning_effort": "low",
        "max_tokens": 8192,
    }


def call_chat_api(api_key: str, question: str) -> dict:
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=build_payload(question),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        sys.exit(f"错误：请求智谱 API 失败（检查网络）：{exc}")

    if resp.status_code != 200:
        # 尽量解析出平台的业务错误码，如 1113 余额不足、1210 参数非法等
        detail = resp.text.strip()
        try:
            err = resp.json().get("error") or {}
            if err:
                detail = f'{err.get("code")}: {err.get("message")}'
        except ValueError:
            pass
        sys.exit(f"错误：API 返回 HTTP {resp.status_code}：{detail}")

    try:
        return resp.json()
    except ValueError:
        sys.exit(f"错误：响应不是合法 JSON：{resp.text[:500]}")


def extract_answer(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        sys.exit(f"错误：响应中没有 choices：{data}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason and finish_reason not in ("stop", None):
        # sensitive（内容安全拦截）/ length（被 max_tokens 截断）等都值得提示
        print(f"[警告] finish_reason={finish_reason}", file=sys.stderr)

    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        sys.exit(f"错误：模型没有返回正文内容：{data}")
    return content.strip()


def extract_sources(data: dict) -> list:
    """从响应顶层 web_search 数组提取来源（title + link），按 link 去重保序。"""
    sources = []
    seen_links = set()
    for item in data.get("web_search") or []:
        link = str(item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append(
            {
                "title": str(item.get("title") or "").strip() or "(无标题)",
                "link": link,
                "media": str(item.get("media") or "").strip(),
                "publish_date": str(item.get("publish_date") or "").strip(),
            }
        )
    return sources


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行：export ZHIPUAI_API_KEY=你的Key")

    data = call_chat_api(api_key, QUESTION)
    answer = extract_answer(data)
    sources = extract_sources(data)

    print(f"问题：{QUESTION}")
    print()
    print("答案：")
    print(answer)
    print()

    if sources:
        print(f"参考来源（接口 web_search 字段真实返回，共 {len(sources)} 条，可直接点开核对）：")
        for i, s in enumerate(sources, 1):
            extra = "，".join(x for x in (s["media"], s["publish_date"]) if x)
            suffix = f"（{extra}）" if extra else ""
            print(f"{i}. {s['title']}{suffix}")
            print(f"   {s['link']}")
    else:
        # 宁可失败也绝不编造来源
        print("参考来源：接口本次没有返回 web_search 引用数组，无法提供可核对的来源。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
