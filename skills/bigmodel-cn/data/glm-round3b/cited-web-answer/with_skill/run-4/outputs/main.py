#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联网问答小工具（智谱开放平台 GLM + 联网搜索）。

流程：
  1. 从环境变量 ZHIPUAI_API_KEY 读取 API Key；
  2. 调用 chat/completions，通过 tools 挂上平台内置的 web_search 工具；
  3. 打印模型回答，以及本次回答实际参考的来源（标题 + 可点击 URL）。

来源可信说明：参考来源直接取自响应体顶层的 web_search 数组（接口真实返回），
不使用模型在正文里凭印象写出的链接。

两个关键参数，缺一不可，否则拿不到可点击的来源链接：
  - web_search.search_result = True     # 不传（默认 False）时响应体里没有 web_search 来源数组
  - search_engine = "search_pro_quark"  # search_std / search_pro 返回的来源 link 恒为空字符串，
                                        # 必须用 search_pro_quark / search_pro_sogou 这类带真实链接的引擎

用法：
  export ZHIPUAI_API_KEY=<你的Key>
  python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
REQUEST_TIMEOUT = 180  # glm-5.3 默认开启深度思考 + 联网检索，耗时较长


def ask_with_web_search(api_key: str) -> dict:
    """调用 chat/completions 并挂联网搜索工具，返回完整响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个联网问答助手。请务必基于联网搜索到的资料回答，"
                    "在正文中用 [来源:ref_N] 标注所引用的来源；"
                    "如果搜索资料不足，请如实说明，不要编造。"
                ),
            },
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro_quark",
                    "search_result": True,  # 必须显式开启，响应体顶层才会带来源数组
                    "count": 10,
                },
            }
        ],
        "max_tokens": 4096,
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
    if resp.status_code != 200:
        # 带出平台错误体，便于排查（如 1113 余额不足、1210 参数非法）
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"接口返回错误: {data['error']}")
    return data


def extract_sources(data: dict) -> list:
    """从响应顶层 web_search 数组提取去重后的来源（只要 link 非空的）。"""
    sources = []
    seen_links = set()
    for item in data.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append(item)
    return sources


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先执行 export ZHIPUAI_API_KEY=<你的Key>",
              file=sys.stderr)
        return 1

    try:
        data = ask_with_web_search(api_key)
    except requests.RequestException as exc:
        print(f"错误：请求智谱接口失败：{exc}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    choices = data.get("choices") or []
    if not choices:
        print(f"错误：响应中没有 choices：{data}", file=sys.stderr)
        return 1

    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()

    print(f"问题：{QUESTION}\n")
    print("回答：")
    print(answer if answer else "（模型未返回内容）")

    sources = extract_sources(data)
    print("\n参考来源（本次联网搜索接口真实返回，可点击核对）：")
    if not sources:
        print("  （接口本次没有返回带链接的来源；请检查 search_engine 是否为"
              "search_pro_quark/search_pro_sogou 等带真实链接的引擎）")
    for idx, item in enumerate(sources, 1):
        title = (item.get("title") or "(无标题)").strip() or "(无标题)"
        link = item["link"].strip()
        extra = " / ".join(
            part for part in (
                (item.get("media") or "").strip(),
                (item.get("publish_date") or "").strip(),
            ) if part
        )
        refer = (item.get("refer") or "").strip()
        prefix = f"[{refer}] " if refer else ""
        suffix = f"（{extra}）" if extra else ""
        print(f"  {idx}. {prefix}{title}{suffix}")
        print(f"     {link}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
