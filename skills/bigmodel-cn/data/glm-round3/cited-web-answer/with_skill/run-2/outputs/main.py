#!/usr/bin/env python3
"""联网问答小工具：用智谱 GLM + 联网搜索回答一个写死的问题，并列出可核对的来源。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

来源说明：引用列表直接取自本次 API 响应顶层的 web_search 数组（接口真实返回的
检索结果），不是模型凭印象生成的链接，可直接点击核对。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
TIMEOUT_SECONDS = 120  # 联网检索 + 生成整体耗时较长，给足超时


def fail(message):
    print(f"错误：{message}", file=sys.stderr)
    sys.exit(1)


def ask_with_web_search(api_key):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",
                    # 关键开关：必须显式传 true，响应体顶层才会带 web_search 来源数组；
                    # 缺省时搜索照常执行，但响应里没有该字段，来源会静默丢失。
                    "search_result": True,
                    # 问题针对 2026 年的动态，限定近一年，减少旧闻干扰
                    "search_recency_filter": "oneYear",
                    "count": 10,
                },
            }
        ],
        # glm-5.3 在标准端点强制开启思考，事实类问答用 low 档足够且响应更快
        "reasoning_effort": "low",
    }

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        fail(f"请求智谱 API 失败：{exc}")

    try:
        body = resp.json()
    except ValueError:
        fail(f"响应不是合法 JSON（HTTP {resp.status_code}）：{resp.text[:300]}")

    if resp.status_code != 200 or "error" in body:
        error = body.get("error") or {}
        fail(
            "API 调用失败：HTTP {}，code={}，message={}".format(
                resp.status_code,
                error.get("code"),
                error.get("message") or resp.text[:300],
            )
        )
    return body


def extract_sources(data):
    """从响应顶层 web_search 数组提取来源，按 link 去重、保持原有顺序。"""
    seen = set()
    sources = []
    for item in data.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        sources.append(
            {
                "title": (item.get("title") or "(无标题)").strip(),
                "link": link,
                "media": (item.get("media") or "").strip(),
                "publish_date": (item.get("publish_date") or "").strip(),
            }
        )
    return sources


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置，请先执行：export ZHIPUAI_API_KEY=你的Key")

    data = ask_with_web_search(api_key)

    choices = data.get("choices") or []
    if not choices:
        fail(f"响应中没有 choices：{json.dumps(data, ensure_ascii=False)[:500]}")
    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")

    print(f"问题：{QUESTION}\n")
    print(answer or f"(模型未返回正文，finish_reason={finish_reason})")

    sources = extract_sources(data)
    print("\n" + "=" * 60)
    if sources:
        print(f"参考来源（共 {len(sources)} 条，摘自本次响应 web_search 字段，接口真实返回）：")
        for idx, s in enumerate(sources, 1):
            meta = "，".join(x for x in (s["media"], s["publish_date"]) if x)
            suffix = f"（{meta}）" if meta else ""
            print(f"\n{idx}. {s['title']}{suffix}")
            print(f"   {s['link']}")
    else:
        print("参考来源：本次响应未返回 web_search 来源数组，无法提供可核对的链接，请谨慎采信上述回答。")


if __name__ == "__main__":
    main()
