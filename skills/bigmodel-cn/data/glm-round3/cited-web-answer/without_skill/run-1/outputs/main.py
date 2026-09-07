#!/usr/bin/env python3
"""联网问答小工具。

写死一个问题，调用智谱 GLM 的联网搜索（web_search 工具）作答，
并把接口真实返回的搜索来源（标题 + 可点击 URL）列在答案之后。

用法：
    export ZHIPUAI_API_KEY="你的 API Key"
    python3 main.py

依赖：仅 requests。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 智谱当前旗舰模型，支持 web_search 内置工具
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

REQUEST_TIMEOUT = 180  # 联网搜索 + 生成可能较慢，放宽超时


def extract_sources(payload):
    """从接口响应中提取联网搜索返回的来源列表。

    只取接口真实返回的数据，绝不凭印象编造链接。按优先级依次尝试：
      1. 响应顶层 web_search 数组（官方文档定义的位置，search_result=true 时返回）；
      2. choices[0].message.web_search（部分版本放在 message 里）；
      3. choices[0].message.tool_calls 中 type=web_search 的 search_result。
    """
    candidates = []

    top = payload.get("web_search")
    if isinstance(top, list):
        candidates.extend(top)

    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        msg_ws = message.get("web_search")
        if isinstance(msg_ws, list):
            candidates.extend(msg_ws)
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("type") == "web_search":
                results = call.get("search_result")
                if isinstance(results, list):
                    candidates.extend(results)

    sources = []
    seen_links = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        link = (item.get("link") or "").strip()
        title = (item.get("title") or "").strip() or "(无标题)"
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append({"title": title, "link": link})
    return sources


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print('错误：请先设置环境变量 ZHIPUAI_API_KEY，例如：export ZHIPUAI_API_KEY="..."',
              file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",  # 必填：搜索引擎
                    "search_result": True,          # 关键：要求接口返回搜索来源详情
                },
            }
        ],
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }

    print("问题：" + QUESTION + "\n")
    try:
        resp = requests.post(API_URL, json=payload, headers=headers,
                             timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print("错误：请求智谱接口失败：" + str(exc), file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print("错误：接口返回 HTTP {}：\n{}".format(resp.status_code, resp.text),
              file=sys.stderr)
        return 1

    try:
        data = resp.json()
    except ValueError:
        print("错误：接口返回了非 JSON 内容：\n" + resp.text, file=sys.stderr)
        return 1

    if data.get("error"):
        print("错误：接口返回业务错误：" + str(data["error"]), file=sys.stderr)
        return 1

    choices = data.get("choices") or []
    answer = (choices[0].get("message") or {}).get("content", "") if choices else ""
    if not answer:
        print("错误：接口未返回回答内容。原始响应：" + str(data), file=sys.stderr)
        return 1

    print(answer)

    sources = extract_sources(data)
    print("\n信息来源（本次接口联网搜索真实返回，可点击核对）：")
    if sources:
        for i, s in enumerate(sources, 1):
            print("{}. {}".format(i, s["title"]))
            print("   " + s["link"])
    else:
        print("（接口本次没有返回 web_search 来源数据，无法提供可核对的链接。）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
