#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网问答小工具。

向智谱开放平台（bigmodel.cn）的 GLM 模型提一个写死的问题，模型联网搜索后作答，
把答案和本次回答实际参考的信息来源（标题 + 可点击 URL）打印到 stdout。

来源取自接口响应中真实返回的 web_search 数组（由 search_result: true 开启），
不是模型凭印象生成的链接，可直接点击核对。

用法：
    export ZHIPUAI_API_KEY="你的 Key"
    python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

# 搜索引擎不能随便选（接入手册实测结论）：
#   * search_std / search_pro：来源的 link 恒为空字符串，只有标题和摘要，没有可点击链接；
#   * search_pro_bing / search_pro_jina / search_pro_quark / search_pro_sogou：link 是真实链接。
# 需要让用户核对来源的场景必须用后一类；想换引擎改这里即可。
SEARCH_ENGINE = "search_pro_bing"
REQUEST_TIMEOUT = 180  # 联网搜索 + 生成耗时较长，超时给足


def ask_with_search(question: str, api_key: str) -> dict:
    """调用 chat/completions 并挂 web_search 工具，返回完整响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    question
                    + "\n\n请基于联网搜索到的资料回答，注意核对信息的发布时间；"
                    "如搜索结果不足以回答，请如实说明。"
                ),
            }
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 必须显式传 true：不传（默认 false）时搜索照常执行、答案照常生成，
                    # 但响应体里完全不会出现 web_search 来源数组，"列出来源"会静默失效。
                    "search_result": True,
                    "search_engine": SEARCH_ENGINE,
                    "count": 10,
                    # 问题针对 2026 年的发布动态，限定一年内的结果最相关
                    "search_recency_filter": "oneYear",
                },
            }
        ],
        "stream": False,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    # 接口出错时 body 是 {"error": {"code": ..., "message": ...}}，原样带出来方便排查
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(
            f"接口返回了非 JSON 内容（HTTP {resp.status_code}）：{resp.text[:500]}"
        )
    if resp.status_code != 200 or "error" in data:
        raise RuntimeError(f"接口调用失败（HTTP {resp.status_code}）：{data}")
    return data


def extract_answer(data: dict):
    """取出回答文本和 finish_reason。"""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return message.get("content") or "", choice.get("finish_reason", "")


def extract_sources(data: dict):
    """取出接口真实返回的搜索来源，过滤无链接项并按 URL 去重。

    返回 (来源列表, 被丢弃条数)。只保留 link 非空的条目——没有链接的来源
    无法点击核对，列出来只会造成"有出处"的假象。
    """
    # 来源数组挂在响应体顶层；保险起见也看一眼 message 层
    sources = data.get("web_search")
    if sources is None:
        message = (data.get("choices") or [{}])[0].get("message") or {}
        sources = message.get("web_search")
    sources = sources or []

    seen = set()
    picked, dropped = [], 0
    for item in sources:
        if not isinstance(item, dict):
            continue
        link = (item.get("link") or "").strip()
        if not link or link in seen:
            dropped += 1
            continue
        seen.add(link)
        picked.append(
            {
                "title": (item.get("title") or "（无标题）").strip(),
                "media": (item.get("media") or "").strip(),
                "link": link,
            }
        )
    return picked, dropped


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）。",
            file=sys.stderr,
        )
        return 1

    try:
        data = ask_with_search(QUESTION, api_key)
    except requests.RequestException as exc:
        print(f"错误：网络请求失败：{exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    answer, finish_reason = extract_answer(data)
    if finish_reason != "stop":
        # 例如 length：思考/生成把 token 预算耗尽，content 可能被截断甚至为空
        print(f"警告：finish_reason = {finish_reason!r}，回答可能不完整。", file=sys.stderr)

    print(f"问题：{QUESTION}")
    print()
    print(answer.strip() or "（模型没有返回内容）")
    print()

    sources, dropped = extract_sources(data)
    print("参考来源（接口真实返回，可点击核对）：")
    if sources:
        for i, item in enumerate(sources, 1):
            byline = f"（{item['media']}）" if item["media"] else ""
            print(f"[{i}] {item['title']}{byline}")
            print(f"     {item['link']}")
    else:
        print("（本次接口没有返回带链接的来源，无法提供可核对的 URL。）")
        print(
            "提示：当前搜索引擎未返回链接，可把 SEARCH_ENGINE 改为 "
            "search_pro_quark / search_pro_sogou / search_pro_jina 再试。"
        )
    if dropped:
        print(f"（另有 {dropped} 条来源因链接为空或重复未列出。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
