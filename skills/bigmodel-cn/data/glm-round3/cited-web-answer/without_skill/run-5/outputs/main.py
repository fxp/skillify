#!/usr/bin/env python3
"""联网问答小工具（智谱 BigModel）。

脚本内置一个问题「2026 年智谱 BigModel 发布了哪些新模型」，调用智谱
chat/completions 接口并开启 web_search 联网搜索，把答案打印到 stdout。
答案下方列出本次回答实际参考的信息来源（标题 + 可点击 URL）——这些
来源只从接口真实返回的 web_search 搜索结果中提取，不由模型凭印象生成。

使用方式：
    export ZHIPUAI_API_KEY="你的 API Key"
    python3 main.py

可选环境变量：
    ZHIPUAI_MODEL  覆盖默认模型（默认 glm-4.6）

依赖：仅 requests（pip install requests）。

接口细节依据官方文档（docs.bigmodel.cn）：
  - 请求：POST https://open.bigmodel.cn/api/paas/v4/chat/completions
  - 开启联网搜索并在响应中回传搜索结果：
        tools: [{"type": "web_search",
                 "web_search": {"enable": true, "search_engine": "search_pro",
                                "search_result": true, "count": 10}}]
  - 搜索结果位于响应体顶层 "web_search" 数组，每条含
    title / link / media / content / refer 等字段。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-4.6"
TIMEOUT_SECONDS = 180  # 联网搜索 + 生成耗时较长，放宽超时

QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"


def build_payload(model: str) -> dict:
    """构造 chat/completions 请求体，开启联网搜索并要求回传搜索结果。"""
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个联网问答助手。请基于联网搜索到的资料回答用户问题，"
                    "在答案中用 [ref_N] 标注关键信息的出处"
                    "（N 与搜索结果里的 refer 编号对应），"
                    "不要编造搜索资料中没有的信息。"
                ),
            },
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",
                    # 关键参数：要求接口把本次搜索命中的网页随响应返回，
                    # 供答案下方列出真实可核对的信息来源。
                    "search_result": True,
                    "count": 10,
                },
            }
        ],
        "stream": False,
    }


def call_api(api_key: str, model: str) -> dict:
    """调用智谱 API，返回解析后的 JSON（出错时打印信息并以非 0 码退出）。"""
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            API_URL,
            headers=headers,
            json=build_payload(model),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        print("错误：请求智谱 API 失败：%s" % exc, file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print("错误：智谱 API 返回 HTTP %d" % resp.status_code, file=sys.stderr)
        try:
            err = resp.json().get("error") or {}
            print("错误信息：%s" % (err.get("message") or resp.text), file=sys.stderr)
        except ValueError:
            print(resp.text, file=sys.stderr)
        sys.exit(1)

    try:
        return resp.json()
    except ValueError:
        print("错误：接口响应不是合法 JSON：%s" % resp.text[:500], file=sys.stderr)
        sys.exit(1)


def extract_answer(data: dict) -> str:
    """提取模型生成的答案正文。"""
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def extract_sources(data: dict) -> list:
    """从响应中提取联网搜索返回的真实来源（标题 + 链接）。

    只使用接口返回的数据，绝不自行编造链接：
      1. 优先读响应体顶层 "web_search" 数组（当前官方文档定义的位置）；
      2. 兼容旧结构：choices[0].message.tool_calls 中 type == "web_search"
         条目下的 search_result 数组。
    """
    raw_results = []
    top_level = data.get("web_search")
    if isinstance(top_level, list):
        raw_results = top_level

    if not raw_results:
        choices = data.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            if tool_call.get("type") == "web_search" and isinstance(
                tool_call.get("search_result"), list
            ):
                raw_results.extend(tool_call["search_result"])

    sources, seen_links = [], set()
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or item.get("url") or "").strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        title = str(item.get("title") or "").strip()
        sources.append(
            {
                "title": title or link,
                "link": link,
                "refer": str(item.get("refer") or "").strip(),
            }
        )
    return sources


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行：\n"
            '  export ZHIPUAI_API_KEY="你的 API Key"',
            file=sys.stderr,
        )
        sys.exit(1)

    model = os.environ.get("ZHIPUAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    data = call_api(api_key, model)

    answer = extract_answer(data)
    sources = extract_sources(data)

    print("问题：%s" % QUESTION)
    print("（模型：%s，联网搜索：已开启）" % model)
    print()
    print("回答：")
    print(answer or "（模型未返回内容）")
    print()
    print(
        "参考来源（共 %d 条，均来自本次接口真实返回的联网搜索结果，"
        "可点击核对）：" % len(sources)
    )
    if not sources:
        print("（接口本次未返回任何搜索来源，请检查 web_search.search_result 是否生效）")
    for index, source in enumerate(sources, start=1):
        refer = "[%s] " % source["refer"] if source["refer"] else ""
        print("%d. %s%s" % (index, refer, source["title"]))
        print("   %s" % source["link"])


if __name__ == "__main__":
    main()
