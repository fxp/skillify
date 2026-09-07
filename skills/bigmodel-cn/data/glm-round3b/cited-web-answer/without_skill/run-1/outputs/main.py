"""联网问答小工具。

调用智谱 BigModel 的对话补全接口并开启平台内置的联网搜索（web_search 工具），
回答一个写死的问题，把答案打印到 stdout；答案下方列出本次回答实际参考的信息来源
（来源标题 + 可点击 URL）。

来源全部取自接口响应中真实返回的结构化搜索结果（web_search.search_result），
不由模型自行生成链接，可直接点击核对。

运行方式：
    ZHIPUAI_API_KEY=你的key python3 main.py

依赖：仅 requests。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4.6"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型"
TIMEOUT_SECONDS = 120  # 联网搜索耗时较长，超时放宽


def build_payload(question: str) -> dict:
    """构造对话补全请求体。

    通过 tools 挂上平台内置的 web_search 联网搜索工具；search_result=True
    要求接口在响应中附带结构化搜索结果，供下方来源列表使用。
    """
    return {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": question},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": "search_pro",
                    "count": 10,
                    "search_result": True,
                },
            }
        ],
        "stream": False,
    }


def extract_sources(resp: dict) -> list:
    """从响应 JSON 中提取搜索结果列表。

    官方文档对结构化搜索结果的位置有过两种表述：响应根级 web_search 数组、
    或 choices[].message.search_result。这里依次尝试所有候选位置，
    保证只取接口真实返回的数据；按 link 去重并保持原始顺序。
    """
    candidates = []
    if isinstance(resp.get("web_search"), list):
        candidates.extend(resp["web_search"])
    for choice in resp.get("choices") or []:
        message = (choice or {}).get("message") or {}
        if isinstance(message.get("search_result"), list):
            candidates.extend(message["search_result"])
    if isinstance(resp.get("search_result"), list):
        candidates.extend(resp["search_result"])

    seen = set()
    sources = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if not link or link in seen:
            continue
        seen.add(link)
        sources.append(item)
    return sources


def print_answer(answer: str, sources: list) -> None:
    print(answer.rstrip())
    print()
    print("=" * 64)
    print("参考来源（接口 web_search 实际返回，可点击核对）：")
    print("=" * 64)
    if not sources:
        print("（本次响应未返回结构化搜索结果，无来源链接可列。）")
        return
    for i, item in enumerate(sources, 1):
        title = (item.get("title") or "(无标题)").strip() or "(无标题)"
        meta = " / ".join(
            x for x in (item.get("media"), item.get("publish_date")) if x
        )
        suffix = f"（{meta}）" if meta else ""
        print(f"[{i}] {title}{suffix}")
        print(item["link"])
        print()


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY。", file=sys.stderr)
        return 1

    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=build_payload(QUESTION),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        print(f"错误：请求接口失败：{exc}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(
            f"错误：接口返回 HTTP {response.status_code}：{response.text}",
            file=sys.stderr,
        )
        return 1

    try:
        data = response.json()
    except ValueError as exc:
        print(f"错误：响应不是合法 JSON：{exc}", file=sys.stderr)
        return 1

    choices = data.get("choices") or []
    answer = ((choices[0] or {}).get("message") or {}).get("content") if choices else ""
    if not answer:
        print(f"错误：响应中没有回答内容：{data}", file=sys.stderr)
        return 1

    print_answer(answer, extract_sources(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
