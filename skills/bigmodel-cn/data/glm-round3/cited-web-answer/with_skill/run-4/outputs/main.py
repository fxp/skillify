#!/usr/bin/env python3
"""联网问答小工具。

脚本内置一个问题「2026 年智谱 BigModel 发布了哪些新模型」，调用智谱开放平台
chat/completions + web_search 联网搜索工具回答，并把本次回答实际参考的信息
来源（标题 + 可点击 URL）打印出来。

来源来自响应体顶层的 web_search 数组（接口真实返回的搜索结果），不是模型
凭印象编的链接。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api"
CHAT_URL = f"{API_BASE}/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def die(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def fetch_answer(api_key: str) -> dict:
    """调用 chat/completions 并启用 web_search 工具，返回解析后的响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的联网问答助手，回答必须基于联网搜索到的资料，不要编造事实。",
            },
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,                     # 启用联网搜索
                    "search_engine": "search_pro",      # 显式指定搜索引擎，不依赖默认值
                    "search_result": True,              # 关键：让接口在响应里带回来源列表（默认 false 不返回）
                    "require_search": True,             # 强制先搜索再回答
                    "search_recency_filter": "oneYear", # 只要近一年的结果，过滤旧闻
                },
            }
        ],
        # glm-5.3 在标准端点无法关闭思考（传 disabled 会报 1210），
        # low 是它允许的最轻档位，事实类检索问答够用且更快。
        "reasoning_effort": "low",
        "stream": False,
    }
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=300,
    )
    if not resp.ok:
        die(f"HTTP {resp.status_code}：{resp.text}")
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        die(f"接口返回错误 {err.get('code')}：{err.get('message')}")
    return data


def extract_sources(data: dict) -> list:
    """收集接口真实返回的搜索来源。

    来源在响应体顶层的 web_search 数组；个别版本也可能挂在 choices[0] 或
    message 下，这里依次兜底，并按 link 去重、保持原始顺序。
    """
    raw = data.get("web_search")
    if not raw:
        choice = (data.get("choices") or [{}])[0]
        raw = (
            choice.get("web_search")
            or (choice.get("message") or {}).get("web_search")
            or []
        )
    seen, items = set(), []
    for it in raw:
        link = (it or {}).get("link")
        if not link or link in seen:
            continue
        seen.add(link)
        items.append(it)
    return items


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY（在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）")

    data = fetch_answer(api_key)

    choices = data.get("choices") or []
    if not choices:
        die(f"响应里没有 choices：{data}")
    finish_reason = choices[0].get("finish_reason")
    if finish_reason not in (None, "stop"):
        print(f"提示：finish_reason={finish_reason}", file=sys.stderr)

    print(f"问题：{QUESTION}\n")
    print(choices[0].get("message", {}).get("content") or "（模型没有返回内容）")

    sources = extract_sources(data)
    print("\n" + "─" * 60)
    if sources:
        print(f"参考来源（接口 web_search 实际返回，共 {len(sources)} 条，可点击核对）：")
        for i, it in enumerate(sources, 1):
            title = it.get("title") or "(无标题)"
            meta = ", ".join(str(x) for x in (it.get("media"), it.get("publish_date")) if x)
            suffix = f"（{meta}）" if meta else ""
            print(f"[{i}] {title}{suffix}")
            print(f"    {it.get('link')}")
    else:
        print("参考来源：接口本次没有返回 web_search 来源列表，无法提供可核对的链接。")


if __name__ == "__main__":
    main()
