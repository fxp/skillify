"""
调用智谱 GLM 模型（chat/completions），挂上内置的联网搜索工具（web_search），
让模型在回答问题时可以查询最新信息，并在回答文本后附上引用来源
（标题 + 链接）列表，方便用户溯源。

仅使用标准库 requests 直接调用 HTTP 接口，不依赖官方 zhipuai SDK。

使用前准备：
    export ZHIPU_API_KEY="你的智谱API Key"   # 从 https://open.bigmodel.cn 控制台获取
    pip install requests

运行：
    python search_chat.py "今天有什么值得关注的AI新闻？"

注意：本文件不会在编写时真实调用智谱 API（没有可用的 Key），仅提供可运行的
参考实现。如果响应体的具体字段名称与智谱后续版本的接口有出入，请对照
最新官方文档微调 extract_citations() 中的取值逻辑（已做了较为宽松/兼容的
字段名探测）。
"""

from __future__ import annotations

import os
import sys
import json
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 智谱开放平台 GLM 系列模型的 Chat Completions 接口地址（OpenAI 兼容风格）
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 从环境变量读取 API Key，避免把密钥硬编码进代码。
# 智谱的 API Key 格式通常形如 "{id}.{secret}"，v4 接口支持直接把完整的
# API Key 作为 Bearer Token 使用（无需像旧版 SDK 那样手动签发 JWT）。
API_KEY_ENV_VAR = "ZHIPU_API_KEY"

# 使用的模型，可按需替换为 glm-4-plus / glm-4-air / glm-4-flash 等。
DEFAULT_MODEL = "glm-4-plus"

REQUEST_TIMEOUT_SECONDS = 60


class GLMAPIError(RuntimeError):
    """封装智谱接口返回的错误信息，方便上层统一处理。"""


def _get_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"未找到环境变量 {API_KEY_ENV_VAR}，请先执行："
            f'\n    export {API_KEY_ENV_VAR}="你的智谱API Key"'
        )
    return api_key


def build_payload(user_query: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """构造带有联网搜索工具的 chat/completions 请求体。"""
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": user_query},
        ],
        # 关闭流式输出，方便一次性拿到完整回答与引用信息。
        "stream": False,
        # 挂载智谱官方内置的联网搜索工具。
        # search_result: "True" 表示要求模型在返回结果中带上检索到的
        # 网页片段（标题/链接/摘要等），供我们提取引用来源。
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": "True",
                    "search_result": "True",
                },
            }
        ],
    }


def call_glm_chat(user_query: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """直接用 requests 调用智谱 GLM 的 chat/completions 接口。"""
    api_key = _get_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = build_payload(user_query, model=model)

    response = requests.post(
        GLM_API_URL,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        raise GLMAPIError(
            f"GLM 接口调用失败，HTTP {response.status_code}: {response.text}"
        )

    data = response.json()

    if isinstance(data, dict) and data.get("error"):
        raise GLMAPIError(f"GLM 接口返回错误: {data['error']}")

    return data


# ---------------------------------------------------------------------------
# 引用来源提取
# ---------------------------------------------------------------------------

# 智谱联网搜索工具返回的检索结果里，标题/链接字段在不同模型版本或接口
# 版本之间命名可能略有差异，这里做兼容处理，多个候选 key 依次尝试。
_TITLE_KEYS = ("title", "name", "media")
_LINK_KEYS = ("link", "url", "source_url")


def _pick_first(d: Dict[str, Any], keys: tuple) -> Optional[str]:
    for key in keys:
        value = d.get(key)
        if value:
            return str(value)
    return None


def _normalize_search_items(raw_items: Any) -> List[Dict[str, str]]:
    """把某个搜索结果字段（可能是 list[dict]）规范化为 {title, link} 列表。"""
    citations: List[Dict[str, str]] = []
    if not isinstance(raw_items, list):
        return citations

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = _pick_first(item, _TITLE_KEYS) or "（未提供标题）"
        link = _pick_first(item, _LINK_KEYS)
        if not link:
            # 没有链接的条目对"溯源"没有意义，跳过。
            continue
        citations.append({"title": title, "link": link})
    return citations


def extract_answer_and_citations(response_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 chat/completions 响应中提取：
      - answer: 模型生成的正文回答
      - citations: [{title, link}, ...] 引用来源列表（已去重）

    智谱的联网搜索结果通常出现在以下位置之一（做兼容探测）：
      1) choices[0]["message"]["tool_calls"]，其中某一项 type == "web_search"，
         对应的检索结果列表在该项的 "web_search" 或 "search_result" 字段里；
      2) 响应顶层的 "web_search" 字段（部分接口版本直接放在顶层）；
      3) choices[0] 层级下的 "web_search" 字段。
    """
    choices = response_json.get("choices") or []
    if not choices:
        raise GLMAPIError(f"响应中没有 choices 字段: {response_json}")

    choice = choices[0]
    message = choice.get("message") or {}
    answer_text = message.get("content") or ""

    raw_citations: List[Dict[str, str]] = []

    # 位置 1：message.tool_calls 中类型为 web_search 的工具调用结果
    for tool_call in message.get("tool_calls") or []:
        if not isinstance(tool_call, dict):
            continue
        if tool_call.get("type") != "web_search":
            continue
        search_items = tool_call.get("web_search") or tool_call.get("search_result")
        raw_citations.extend(_normalize_search_items(search_items))

    # 位置 2：响应顶层
    if not raw_citations and isinstance(response_json.get("web_search"), list):
        raw_citations.extend(_normalize_search_items(response_json["web_search"]))

    # 位置 3：choice 层级
    if not raw_citations and isinstance(choice.get("web_search"), list):
        raw_citations.extend(_normalize_search_items(choice["web_search"]))

    # 按 link 去重，保持原有出现顺序
    seen_links = set()
    citations: List[Dict[str, str]] = []
    for c in raw_citations:
        if c["link"] in seen_links:
            continue
        seen_links.add(c["link"])
        citations.append(c)

    return {"answer": answer_text, "citations": citations}


def format_answer_with_citations(answer: str, citations: List[Dict[str, str]]) -> str:
    """把正文回答和引用来源列表拼接成便于展示给用户的最终文本。"""
    if not citations:
        return answer

    lines = [answer.rstrip(), "", "参考来源：""".rstrip("：") + "："]
    for idx, c in enumerate(citations, start=1):
        lines.append(f"[{idx}] {c['title']} - {c['link']}")

    return "\n".join(lines)


def ask_with_web_search(user_query: str, model: str = DEFAULT_MODEL) -> str:
    """对外的主入口：提问 -> 联网搜索增强回答 -> 附带引用来源的最终文本。"""
    response_json = call_glm_chat(user_query, model=model)
    result = extract_answer_and_citations(response_json)
    return format_answer_with_citations(result["answer"], result["citations"])


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "最近一周有哪些值得关注的科技新闻？"

    try:
        final_text = ask_with_web_search(query)
    except (GLMAPIError, RuntimeError) as exc:
        print(f"调用失败: {exc}", file=sys.stderr)
        sys.exit(1)

    print(final_text)


if __name__ == "__main__":
    main()
