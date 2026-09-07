#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网问答小工具（智谱 BigModel）

- 问题写死在 QUESTION 常量中
- 调用智谱 chat/completions 接口，通过 web_search 工具联网搜索后作答
- 答案打印到 stdout
- 答案下方列出本次回答实际参考的信息来源（标题 + URL），
  来源全部取自接口响应中的 web_search 字段，绝不由模型凭印象编造

运行方式：
    export ZHIPUAI_API_KEY=你的APIKey
    python3 main.py
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 默认用当前旗舰模型，可用环境变量 ZHIPUAI_MODEL 覆盖（如 glm-4.6 / glm-4.5-air）
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-5.3")
TIMEOUT = (10, 180)  # (连接超时, 读取超时)，单位秒；联网搜索+生成较慢，读超时给足

QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def build_payload(question: str) -> dict:
    """构造 chat/completions 请求体，开启 web_search 工具并要求回传搜索结果。"""
    return {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个联网问答助手。请主要依据联网搜索到的新鲜资料回答用户问题，"
                    "在回答中用 [序号] 标注引用来源；如搜索结果不足以回答，请如实说明，"
                    "不要编造不存在的信息或链接。"
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
                    # 关键：search_result=True 时，接口会在响应的 web_search 字段里
                    # 回传真实命中的网页列表（title/link 等），供下方原文摘出
                    "search_result": True,
                },
            }
        ],
        "stream": False,
    }


def load_api_key() -> str:
    """从环境变量读取 API Key，缺失时直接报错退出。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未检测到环境变量 ZHIPUAI_API_KEY，请先 export 后再运行。", file=sys.stderr)
        sys.exit(1)
    return api_key


def call_api(question: str, api_key: str) -> dict:
    """发起请求并返回解析后的 JSON；出错时打印原因并以非零码退出。"""
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            API_URL, headers=headers, json=build_payload(question), timeout=TIMEOUT
        )
    except requests.RequestException as exc:
        print("错误：请求智谱接口失败：{}".format(exc), file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print("错误：接口返回 HTTP {}：".format(resp.status_code), file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    try:
        return resp.json()
    except ValueError:
        print("错误：接口响应不是合法 JSON：\n{}".format(resp.text), file=sys.stderr)
        sys.exit(1)


def extract_answer(payload: dict) -> str:
    """从响应中取出模型生成的答案文本。"""
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def extract_sources(payload: dict) -> list:
    """只从接口响应里提取搜索来源，不做任何构造或猜测。

    新版接口把结果放在响应顶层 web_search 数组；旧版放在
    choices[].message.web_search。两处都检查，按 link 去重，保持接口返回顺序。
    """
    raw = []
    top = payload.get("web_search")
    if isinstance(top, list):
        raw.extend(top)
    for choice in payload.get("choices") or []:
        ws = (choice.get("message") or {}).get("web_search")
        if isinstance(ws, list):
            raw.extend(ws)

    sources, seen_links = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
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
    api_key = load_api_key()

    print("问题：{}".format(QUESTION))
    print("=" * 64)

    payload = call_api(QUESTION, api_key)

    answer = extract_answer(payload)
    if not answer:
        print("错误：接口未返回答案文本，原始响应如下：", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

    print("答案：")
    print(answer)
    print("=" * 64)

    sources = extract_sources(payload)
    if not sources:
        # 宁可失败也不编造来源
        print(
            "错误：本次接口响应中没有返回任何搜索来源，无法列出可核对的引用。\n"
            "原始响应如下：",
            file=sys.stderr,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

    print("参考来源（共 {} 条，均取自本次接口响应的 web_search 字段）：".format(len(sources)))
    for idx, src in enumerate(sources, 1):
        meta = " · ".join(x for x in (src["media"], src["publish_date"]) if x)
        meta = "（{}）".format(meta) if meta else ""
        print("[{}] {}{}".format(idx, src["title"], meta))
        print("    {}".format(src["link"]))


if __name__ == "__main__":
    main()
