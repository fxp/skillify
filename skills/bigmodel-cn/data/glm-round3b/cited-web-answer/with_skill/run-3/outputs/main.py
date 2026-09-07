#!/usr/bin/env python3
"""联网问答小工具。

问一个写死的问题（2026 年智谱 BigModel 发布了哪些新模型），调用智谱 GLM 模型
并挂上平台内置的联网搜索工具作答；答案下方列出本次回答实际参考的信息来源
（标题 + 可点击 URL）。来源只取接口响应里真实返回的 web_search 数组，
不由模型凭印象生成。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys
import time

import requests

API_KEY_ENV = "ZHIPUAI_API_KEY"
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
TIMEOUT = 300  # 联网搜索 + 生成较慢，放宽整体超时

QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"

# web_search 工具配置。两个容易踩的坑：
# 1) search_result 必须显式为 true，响应体顶层才会带 web_search 来源数组；
#    不传时（默认 false）搜索照常执行、正文正常生成，但响应里完全没有
#    web_search 字段，"列出信息来源"会静默失效。
# 2) search_engine 不能选 search_std / search_pro——实测这两个引擎返回的来源
#    link 恒为空字符串；要拿到可点击、可核对的链接，必须用 search_pro_sogou /
#    search_pro_quark / search_pro_bing / search_pro_jina 这类引擎。
WEB_SEARCH_TOOL = {
    "type": "web_search",
    "web_search": {
        "enable": True,
        "search_result": True,                 # 让响应顶层返回来源数组（关键）
        "search_engine": "search_pro_sogou",   # 该引擎返回的 link 非空，可点击
        "search_intent": True,
        "count": 10,
        "search_recency_filter": "oneYear",    # 问的是 2026 年新模型，限定近一年
        "content_size": "high",                # 更详细的摘要，回答依据更充分
    },
}


def ask_with_search(api_key: str) -> dict:
    """调用 chat/completions（带联网搜索工具），返回解析后的响应 JSON。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的联网问答助手。请只依据联网搜索返回的资料回答，"
                    "写明模型名称、发布时间等关键事实；搜索资料里没有的信息不要编造。"
                ),
            },
            {"role": "user", "content": QUESTION},
        ],
        "tools": [WEB_SEARCH_TOOL],
        "stream": False,
        # glm-5.3 在标准端点强制开启思考（仅接受 low/high/max），low 接近不思考，
        # 对"搜索 + 汇总事实"这类问题足够，且能明显缩短等待时间。
        "reasoning_effort": "low",
    }

    last_error = "未知错误"
    for attempt in range(3):  # 对网络异常 / 429 / 5xx 做简单指数退避重试
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"网络请求失败：{exc}"
            time.sleep(2 ** attempt)
            continue

        if resp.status_code >= 400:
            # 智谱把业务错误码放在响应体 error 字段里（如 1113 余额不足、1210 参数非法）
            try:
                err = resp.json().get("error", {})
                detail = f"{err.get('code', '')} {err.get('message', '')}".strip()
            except ValueError:
                detail = resp.text[:500]
            last_error = f"HTTP {resp.status_code}：{detail}"
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            break  # 其余 4xx 属于配置/参数问题，重试无意义

        return resp.json()

    raise SystemExit(f"调用智谱 API 失败：{last_error}")


def extract_sources(data: dict) -> list:
    """从响应顶层 web_search 数组提取真实返回的来源，过滤空 link 并按 URL 去重。"""
    seen = set()
    sources = []
    for item in data.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        sources.append(item)
    return sources


def print_result(data: dict) -> None:
    choices = data.get("choices") or []
    if not choices:
        raise SystemExit(f"响应里没有 choices：{data}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason not in (None, "stop"):
        # sensitive / network_error / length 等，异常终止时正文可能不完整
        print(f"注意：finish_reason={finish_reason}，回答可能不完整。", file=sys.stderr)

    answer = (choice.get("message") or {}).get("content") or "（模型没有返回正文）"

    print(f"问题：{QUESTION}\n")
    print("回答：")
    print(answer)
    print()

    sources = extract_sources(data)
    print("─" * 60)
    if sources:
        print(f"参考来源（共 {len(sources)} 条，均为接口真实返回的 web_search 结果，可点击核对）：")
        for i, item in enumerate(sources, 1):
            title = (item.get("title") or "（无标题）").strip()
            meta = " | ".join(
                part
                for part in ((item.get("media") or "").strip(), (item.get("publish_date") or "").strip())
                if part
            )
            print(f"[{i}] {title}")
            print(f"    {item['link'].strip()}")
            if meta:
                print(f"    （{meta}）")
    else:
        print("参考来源：本次接口未返回带链接的来源（web_search 数组缺失或 link 全为空）。")


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise SystemExit(f"请先设置环境变量 {API_KEY_ENV}（智谱开放平台 API Key）")
    data = ask_with_search(api_key)
    print_result(data)


if __name__ == "__main__":
    main()
