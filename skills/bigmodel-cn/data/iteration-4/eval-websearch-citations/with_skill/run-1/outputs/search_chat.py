#!/usr/bin/env python3
"""
调用智谱 GLM 模型对话接口（chat/completions）时挂上内置的 web_search 工具，
让模型在回答问题时可以联网检索最新信息，并在回答正文之后附上引用来源
（标题 + 链接）列表，方便用户溯源。

仅使用标准库 requests 直接调 HTTP 接口，不依赖官方 zhipuai SDK。

参考文档：docs.bigmodel.cn -> chat/completions -> tools -> web_search
- Base URL 固定为 https://open.bigmodel.cn/api/
- 鉴权：HTTP Bearer，请求头 Authorization: Bearer <API_KEY>
- web_search 工具必须显式传 web_search.search_result = True，
  响应体顶层才会带上 "web_search" 引用来源数组
  （字段包含 icon/title/link/media/publish_date/content/refer）。
  不传这个字段时搜索依旧会正常执行、结果依旧会用于生成回答，
  但响应里不会出现 "web_search" 字段，代码读 response.get("web_search")
  只会静默拿到 None，"展示信息来源" 的需求会悄悄失效——因此下面显式传了它。
- search_engine 官方文档标记为必填，虽然实测省略也不报错，但为了不依赖
  未公开保证的默认行为，这里始终显式传 search_engine。

使用前：
    export ZHIPUAI_API_KEY="你的真实 API Key"
    python search_chat.py "今天有什么科技新闻？"

注意：本脚本中的 API Key 只是从环境变量读取的占位符，不包含真实密钥，
也没有实际发起过网络请求验证——请在你自己的环境里配置好 Key 后再运行。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# API Key 从环境变量读取，绝不要把真实 Key 硬编码进代码。
# 这里的默认值只是一个占位符，用于让脚本在没有配置环境变量时也能被
# 静态检查/直接运行到"发起 HTTP 请求"这一步（会因为 Key 无效而被服务端拒绝）。
API_KEY = os.environ.get("ZHIPUAI_API_KEY", "YOUR_API_KEY_PLACEHOLDER")

DEFAULT_MODEL = "glm-5.3"


def build_payload(
    question: str,
    model: str = DEFAULT_MODEL,
    search_engine: str = "search_pro",
    count: int = 5,
) -> dict[str, Any]:
    """构造带 web_search 工具的 chat/completions 请求体。

    - web_search.search_result 必须显式设为 True，否则响应体里不会带
      顶层 "web_search" 引用来源数组（详见文件头部说明）。
    - search_engine 显式传值（search_std / search_pro / search_pro_sogou /
      search_pro_quark），不依赖未文档化的默认行为。
    - count 控制返回的搜索结果条数（1-50），同时也决定了引用来源列表的
      条目数量上限。
    """
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个乐于助人的助手。如果问题涉及最新信息、时效性内容"
                    "或你不确定的事实，请使用联网搜索工具查证后再回答。"
                ),
            },
            {"role": "user", "content": question},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": search_engine,
                    "count": count,
                    # 必须显式为 True，响应体才会带 "web_search" 引用来源数组。
                    "search_result": True,
                },
            }
        ],
    }


def call_glm_with_web_search(
    question: str,
    model: str = DEFAULT_MODEL,
    search_engine: str = "search_pro",
    count: int = 5,
    timeout: int = 60,
) -> dict[str, Any]:
    """调用 chat/completions 接口，返回原始响应 JSON（dict）。"""
    if not API_KEY or API_KEY == "YOUR_API_KEY_PLACEHOLDER":
        raise RuntimeError(
            "未配置有效的 API Key：请先执行 "
            "`export ZHIPUAI_API_KEY=你的真实Key` 后再运行本脚本。"
        )

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = build_payload(
        question, model=model, search_engine=search_engine, count=count
    )

    resp = requests.post(BASE_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def extract_answer(response_json: dict[str, Any]) -> str:
    """从响应中取出模型的自然语言回答正文。"""
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def extract_citations(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    """取出响应体顶层的 web_search 引用来源数组。

    每条记录可能包含 icon/title/link/media/publish_date/content/refer 等
    字段；只要开启了 web_search.search_result=True 就会有这个顶层字段
    （命中搜索意图时是非空数组，未触发联网检索时可能是空数组）。
    """
    return response_json.get("web_search") or []


def format_citations(citations: list[dict[str, Any]]) -> str:
    """把引用来源数组格式化成"标题 + 链接"列表，方便用户溯源。"""
    if not citations:
        return ""

    lines = ["参考来源："]
    for idx, item in enumerate(citations, start=1):
        title = (item.get("title") or "").strip() or "（无标题）"
        link = (item.get("link") or "").strip() or "（无链接）"
        lines.append(f"{idx}. {title} - {link}")
    return "\n".join(lines)


def answer_with_citations(question: str, model: str = DEFAULT_MODEL) -> str:
    """一站式：提问 -> 联网搜索增强回答 -> 正文后附引用来源列表。"""
    response_json = call_glm_with_web_search(question, model=model)

    answer = extract_answer(response_json)
    citations = extract_citations(response_json)
    citations_block = format_citations(citations)

    if citations_block:
        return f"{answer}\n\n{citations_block}"
    return answer


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "今天有哪些值得关注的科技新闻？"

    try:
        result = answer_with_citations(question)
    except requests.exceptions.HTTPError as exc:
        # 常见于 API Key 无效/过期、参数非法等，把服务端返回的错误详情打印出来
        # 方便排查（响应体通常是 {"error": {"code": ..., "message": ...}}）。
        detail = ""
        if exc.response is not None:
            try:
                detail = json.dumps(exc.response.json(), ensure_ascii=False)
            except ValueError:
                detail = exc.response.text
        print(f"请求失败：{exc}\n{detail}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"网络请求异常：{exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
