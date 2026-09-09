#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 联网搜索回答「2026 年中国新能源汽车出口的主要目的地国家有哪些」。

要求：答案完整（不被截断）+ 至少 2 条可点击的来源链接，任一不满足都明确报错退出。
只依赖 requests（外加标准库），python3 main.py 直接运行。

关键防坑点（来自 bigmodel-cn 技能包的实测结论，与官方文档 docs.bigmodel.cn 交叉核对过）：
1. search_engine 不能用 search_std / search_pro —— 它们返回的来源 link 恒为空字符串，
   要拿到真实可点击链接必须用 search_pro_quark / search_pro_sogou / search_pro_bing。
2. web_search 工具必须显式传 search_result: true，否则响应体里根本不出现来源数组，
   搜索照跑、答案照给，只是没有出处（静默失效）。
3. 思考 token 计入 max_tokens：预算不足时 finish_reason=length、答案被截断。
   判断答案是否完整的依据是 finish_reason == "stop"，而不是 content 是否为空。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 通用旗舰，1M 上下文 / 128K 最大输出；同步端点不会静默换模型
QUESTION = (
    "2026 年中国新能源汽车出口的主要目的地国家有哪些？"
    "请基于联网搜索到的最新资料，完整列出主要目的地国家并作简要说明。"
)

# 只用实测会返回真实链接的引擎，按优先级回退：
# quark/sogou 是官方参数表在列的，bing 实测可用但未列入官方参数表
SEARCH_ENGINES = ("search_pro_quark", "search_pro_sogou", "search_pro_bing")
MIN_SOURCES = 2
# glm-5.3 思考强制开启且思考 token 计入 max_tokens，给足预算防止答案被截断（上限 131072）
MAX_TOKENS = 16384


class AnswerError(Exception):
    """答案不完整或来源不合格时抛出，统一转成明确的报错信息。"""


def get_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        raise AnswerError(
            "未配置 API Key：请先执行 export ZHIPUAI_API_KEY=<你的 Key> 再运行。"
            "Key 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取。"
        )
    return key


def ask_with_search(api_key, engine):
    """带联网搜索工具调用 chat/completions，返回完整响应 dict。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    "search_result": True,  # 不显式传 true，响应里不会带来源数组
                    "search_recency_filter": "oneYear",  # 2026 年的资料，限近一年
                    "content_size": "high",
                    "count": 10,
                },
            }
        ],
        "max_tokens": MAX_TOKENS,
    }
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=(15, 300),
    )
    if resp.status_code != 200:
        raise AnswerError(
            f"调用 chat/completions 失败：HTTP {resp.status_code}，响应片段：{resp.text[:500]}"
        )
    try:
        data = resp.json()
    except ValueError:
        raise AnswerError(f"响应不是合法 JSON：{resp.text[:500]}")
    if isinstance(data.get("error"), dict):
        err = data["error"]
        raise AnswerError(f"API 返回错误：code={err.get('code')}，{err.get('message')}")
    return data


def extract_answer(data):
    """校验并取出完整答案；不完整就报错说明原因。"""
    choices = data.get("choices") or []
    if not choices:
        raise AnswerError(f"响应里没有 choices，无法取答案。响应片段：{str(data)[:500]}")
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    content = ((choice.get("message") or {}).get("content") or "").strip()
    # length=被 max_tokens 截断；sensitive=内容安全拦截；network_error=模型推理异常
    if finish_reason != "stop":
        raise AnswerError(
            f"答案不完整：finish_reason={finish_reason!r}"
            "（length=被 max_tokens 截断；sensitive=内容安全拦截；"
            "network_error=模型推理异常），当前输出 "
            f"{len(content)} 字。请调大 MAX_TOKENS 或重试，不要把半截答案贴进周报。"
        )
    if not content:
        raise AnswerError("答案为空：finish_reason=stop 但 content 是空字符串，请重试。")
    return content


def extract_sources(data):
    """从响应里提取去重后的真实来源链接（http 开头才要）。"""
    # 实测来源数组在响应顶层 web_search 字段；官方文档页写的 search_result 也兜底读一下
    items = data.get("web_search") or data.get("search_result") or []
    sources, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if link.startswith("http") and link not in seen:
            seen.add(link)
            sources.append(
                {
                    "link": link,
                    "title": str(item.get("title") or "").strip(),
                    "media": str(item.get("media") or "").strip(),
                    "publish_date": str(item.get("publish_date") or "").strip(),
                }
            )
    return sources


def run():
    api_key = get_api_key()
    last_error = None
    for engine in SEARCH_ENGINES:
        try:
            data = ask_with_search(api_key, engine)
            answer = extract_answer(data)
            sources = extract_sources(data)
            if len(sources) < MIN_SOURCES:
                raise AnswerError(
                    f"来源链接不足：引擎 {engine} 只返回 {len(sources)} 条 http 开头的真实链接"
                    f"（要求至少 {MIN_SOURCES} 条），无法人工复核出处。"
                    f"原始来源条目数：{len(data.get('web_search') or data.get('search_result') or [])}"
                )
            return answer, sources, engine, data
        except AnswerError as exc:
            last_error = exc
            print(f"[警告] 引擎 {engine} 未达标，换下一个引擎重试：{exc}", file=sys.stderr)
        except requests.RequestException as exc:
            last_error = AnswerError(f"网络请求失败：{exc!r}")
            print(f"[警告] 引擎 {engine} 请求异常，换下一个引擎重试：{exc}", file=sys.stderr)
    raise last_error


def main():
    try:
        answer, sources, engine, data = run()
    except AnswerError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[信息] 模型 {data.get('model', MODEL)}，搜索引擎 {engine}，"
          f"来源 {len(sources)} 条，finish_reason=stop")
    print()
    print(answer)
    print()
    print("来源链接（供人工复核）：")
    for idx, src in enumerate(sources, 1):
        who = src["media"] or src["title"] or "未知来源"
        when = f"，{src['publish_date']}" if src["publish_date"] else ""
        print(f"[{idx}] {src['title'] or who}")
        print(f"    {src['link']}（{who}{when}）")


if __name__ == "__main__":
    main()
