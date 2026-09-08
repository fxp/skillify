"""联网问答小工具：问「2026 年智谱 BigModel 发布了哪些新模型」，用智谱 GLM 联网搜索回答。

答案打印到 stdout，末尾附上本次回答实际参考的信息来源（标题 + 可点击 URL）。
来源取自 chat/completions 响应体顶层的 web_search 数组——即接口真实返回的检索结果，
不是模型自己编的链接。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

两个必须注意的接口坑（已用真实 API 验证）：
  1. search_engine 选 search_std / search_pro 时，返回来源的 link 字段恒为空字符串，
     只有 search_pro_sogou / _quark / _jina / _bing 才带真实可点击链接。
  2. 不显式传 web_search.search_result: true 时，搜索照跑、答案照给，
     但响应体里根本没有 web_search 来源数组，引用会静默丢失。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年智谱 BigModel 发布了哪些新模型？"

# glm-5.3 在标准端点强制开启深度思考，且思考 token 计入 max_tokens，
# 预算给足，避免 finish_reason=length 导致正文为空。
MAX_TOKENS = 16384
# 联网检索 + 思考 + 生成的总耗时较长，超时放宽。
TIMEOUT_SECONDS = 300


def ask_with_web_search(question: str, api_key: str) -> dict:
    """带联网搜索调用 chat/completions，返回完整响应 JSON。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": MAX_TOKENS,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 必须用带链接的引擎，不能用 search_pro / search_std（见模块 docstring 坑 1）
                    "search_engine": "search_pro_sogou",
                    # 必须显式开启，否则响应里没有 web_search 来源数组（见模块 docstring 坑 2）
                    "search_result": True,
                    "search_recency_filter": "oneYear",
                },
            }
        ],
    }
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def extract_sources(response: dict) -> list:
    """从响应里提取去重后的真实来源列表（仅保留 link 非空的条目）。"""
    seen_links = set()
    sources = []
    for item in response.get("web_search") or []:
        link = (item.get("link") or "").strip()
        title = (item.get("title") or "").strip() or "(无标题)"
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        sources.append({"title": title, "link": link})
    return sources


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY。请先执行：export ZHIPUAI_API_KEY=你的Key",
            file=sys.stderr,
        )
        return 1

    try:
        response = ask_with_web_search(QUESTION, api_key)
    except requests.RequestException as exc:
        print(f"错误：请求智谱 API 失败：{exc}", file=sys.stderr)
        return 1

    choices = response.get("choices") or []
    if not choices:
        print(f"错误：响应中没有 choices。完整响应：{response}", file=sys.stderr)
        return 1

    message = choices[0].get("message") or {}
    answer = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")

    if not answer:
        # finish_reason=length 说明思考 token 吃光了 max_tokens 预算，而不是参数问题
        print(
            f"错误：模型未返回正文（finish_reason={finish_reason}）。"
            "若为 length，请调大 MAX_TOKENS 后重试。",
            file=sys.stderr,
        )
        return 1
    if finish_reason == "length":
        print("警告：finish_reason=length，回答可能被截断。", file=sys.stderr)

    print(answer)

    sources = extract_sources(response)
    print("\n" + "=" * 60)
    print("本次回答参考的信息来源（来自接口返回的 web_search 结果）：")
    print("=" * 60)
    if not sources:
        print("（接口本次没有返回任何带链接的来源，无法提供可核对的 URL。）")
        return 1
    for i, source in enumerate(sources, start=1):
        print(f"{i}. {source['title']}")
        print(f"   {source['link']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
