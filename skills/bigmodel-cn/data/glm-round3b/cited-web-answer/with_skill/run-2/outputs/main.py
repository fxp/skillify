#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网问答小工具：问一个写死的问题，用智谱 GLM 模型 + 联网搜索回答，
并列出本次回答实际依据的来源（标题 + 可点击 URL）。

来源只从接口响应体顶层的 `web_search` 数组里读（平台注入的真实搜索结果），
绝不从模型正文里抽链接，保证列出的每条 URL 都能点开核对。

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

# 关键点：search_std / search_pro 返回的来源 link 恒为空字符串（HTTP 200、条数正常、
# 标题摘要齐全，唯独链接是空的——典型的静默失效，已于 2026-09 用真实 API 验证）。
# 要拿到可点击的来源链接，必须用下面这几个引擎，按优先级依次尝试：
SEARCH_ENGINES = ("search_pro_quark", "search_pro_bing", "search_pro_sogou")
REQUEST_TIMEOUT = 180  # 秒


def ask_with_web_search(api_key, engine):
    """带联网搜索调用 chat/completions，返回 (回答文本, 来源列表, finish_reason)。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是联网问答助手。请仅依据联网搜索返回的资料回答，"
                    "不要凭记忆编造；搜索资料里没有的信息要如实说明。"
                ),
            },
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    # 固定搜索词，避免模型自行改写偏题（该字段限长 70 字符，本问题远小于）
                    "search_query": QUESTION,
                    # 必须显式传 true：不传（默认 false）时搜索照常执行、回答正常生成，
                    # 但响应体顶层不会带 web_search 来源数组，来源会"静默消失"
                    "search_result": True,
                    # 只保留近一年的结果，聚焦 2026 年的新发布
                    "search_recency_filter": "oneYear",
                    "count": 10,
                },
            }
        ],
        # glm-5.3 在标准端点强制思考，low 档实测接近不思考，能明显降低延迟，
        # 对"总结搜索结果"这类问答足够
        "reasoning_effort": "low",
        "max_tokens": 2048,
    }

    resp = requests.post(
        API_URL,
        headers={"Authorization": "Bearer " + api_key},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        # 平台错误信息在响应体 error 字段里，尽量带出来方便排查
        try:
            err = resp.json().get("error") or {}
            detail = "%s %s" % (err.get("code"), err.get("message")) if err else resp.text[:300]
        except ValueError:
            detail = resp.text[:300]
        raise RuntimeError("HTTP %s: %s" % (resp.status_code, detail))

    data = resp.json()
    if "error" in data:
        raise RuntimeError("接口返回错误: %s" % data["error"])

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("响应里没有 choices: %s" % str(data)[:300])
    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")
    # 只信任接口真实返回的来源，过滤掉 link 为空的条目
    sources = [
        s
        for s in (data.get("web_search") or [])
        if isinstance(s, dict) and (s.get("link") or "").strip()
    ]
    return answer, sources, finish_reason


def dedupe_sources(sources):
    """按 URL 去重，保持原有顺序。"""
    seen, out = set(), []
    for s in sources:
        link = s["link"].strip()
        if link in seen:
            continue
        seen.add(link)
        out.append({"title": s.get("title") or "", "link": link,
                    "media": s.get("media") or "", "publish_date": s.get("publish_date") or ""})
    return out


def print_result(engine, answer, sources):
    print("问题：%s" % QUESTION)
    print("（模型 %s + 联网搜索 %s）\n" % (MODEL, engine))
    print("─" * 60)
    print(answer or "（模型没有返回回答内容）")
    print("─" * 60)
    sources = dedupe_sources(sources)
    if sources:
        print("\n参考来源（接口 web_search 字段真实返回，共 %d 条，可点击核对）：" % len(sources))
        for i, s in enumerate(sources, 1):
            meta = "，".join(x for x in (s["media"], s["publish_date"]) if x)
            suffix = "（%s）" % meta if meta else ""
            print("  %d. %s%s" % (i, s["title"].strip() or "（无标题）", suffix))
            print("     %s" % s["link"])
    else:
        print("\n参考来源：接口本次没有返回带链接的搜索来源（原因见 stderr 警告）。")


def main():
    api_key = (os.environ.get("ZHIPUAI_API_KEY") or "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=你的Key",
              file=sys.stderr)
        return 1

    best_without_links = None  # (engine, answer)：没拿到可点击来源但成功回答时的兜底
    for engine in SEARCH_ENGINES:
        try:
            answer, sources, finish_reason = ask_with_web_search(api_key, engine)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print("[警告] 搜索引擎 %s 调用失败：%s" % (engine, exc), file=sys.stderr)
            continue
        if finish_reason not in (None, "stop"):
            print("[警告] 引擎 %s 的 finish_reason=%s" % (engine, finish_reason), file=sys.stderr)
        if answer and sources:
            print_result(engine, answer, sources)
            return 0
        if answer and best_without_links is None:
            best_without_links = (engine, answer)
        print("[警告] 引擎 %s 未返回带链接的来源，换下一个引擎重试" % engine, file=sys.stderr)

    if best_without_links:
        engine, answer = best_without_links
        print_result(engine, answer, [])
        print("注意：已尝试的全部搜索引擎（%s）本次都没有返回可点击的来源链接，"
              "上述回答无法附来源核对。" % ", ".join(SEARCH_ENGINES), file=sys.stderr)
        return 1
    print("错误：所有搜索引擎均调用失败，未获得回答。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
