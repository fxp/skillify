#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 联网搜索回答「2026 年中国新能源汽车出口的主要目的地国家有哪些」。

硬性要求（不满足就报错退出，绝不输出半截结果）：
1. 答案完整：finish_reason 必须是 "stop"，为 "length" 说明被 max_tokens 截断；
2. 来源可核：响应 web_search 数组中至少 2 条 http 开头的真实链接。

API Key 从环境变量 ZHIPUAI_API_KEY 读取；仅依赖 requests。
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = "2026 年中国新能源汽车出口的主要目的地国家有哪些？"
MIN_LINKS = 2

# search_std / search_pro 返回的来源 link 恒为空串（HTTP 200、条数正常，只有链接为空），
# 必须用实测带真实链接的引擎；search_pro_quark / search_pro_sogou 官方参数表在列且实测 link 非空。
SEARCH_ENGINES = ["search_pro_quark", "search_pro_sogou"]

# glm-5.3 在标准端点强制开启思考，且思考 token 计入 max_tokens，
# 预算给小了会 finish_reason=length、content 为空——显式给足。
MAX_TOKENS = 8192

USER_PROMPT = (
    f"{QUESTION}\n"
    "请基于联网搜索到的最新资料回答：列出 2026 年以来中国新能源汽车出口的主要目的地国家，"
    "并简要说明各国对应的出口规模、增速或代表车型等依据。请完整作答，不要只写一半；"
    "回答正文里不用附参考链接，来源列表由程序单独输出。"
)

HTTP_TIMEOUT = 180          # 联网搜索 + 思考模型，整体耗时较长
MAX_RETRIES = 3             # 仅对 429 / 5xx 退避重试，4xx 配置类错误直接报错


def fail(reason: str) -> None:
    print(f"错误：{reason}", file=sys.stderr)
    sys.exit(1)


def chat_once(api_key: str, engine: str) -> dict:
    """调用一次 chat/completions（非流式 + web_search 工具），带 429/5xx 退避重试。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": USER_PROMPT}],
        "stream": False,  # 必须非流式，响应体顶层才会带完整的 web_search 引用数组
        "max_tokens": MAX_TOKENS,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 引擎选错 = 拿不到任何可点击链接（link 恒为空串的静默失效）
                    "search_engine": engine,
                    # 不显式传 true，响应里根本没有 web_search 数组——搜索照跑、答案照给、就是没出处
                    "search_result": True,
                    "require_search": True,
                    "count": 10,
                    "search_recency_filter": "oneYear",
                    "content_size": "high",
                },
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            fail(f"请求智谱 API 网络异常（已重试 {MAX_RETRIES} 次）：{exc}")

        if resp.status_code in (429,) or resp.status_code >= 500:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)  # 指数退避，避免固定间隔加重限流
                continue
            fail(f"智谱 API 持续返回 HTTP {resp.status_code}（已重试 {MAX_RETRIES} 次）：{resp.text[:500]}")

        try:
            data = resp.json()
        except ValueError:
            fail(f"智谱 API 返回了无法解析的非 JSON 内容（HTTP {resp.status_code}）：{resp.text[:500]}")

        api_error = data.get("error") if isinstance(data, dict) else None
        if api_error:
            fail(
                f"智谱 API 返回业务错误（HTTP {resp.status_code}，"
                f"code={api_error.get('code')}）：{api_error.get('message')}"
            )
        if resp.status_code != 200:
            fail(f"智谱 API 返回 HTTP {resp.status_code}：{resp.text[:500]}")
        return data

    fail("智谱 API 重试次数耗尽")  # 理论上到不了这里


def check_answer_complete(data: dict) -> str:
    """校验答案完整性，返回正文；不完整就地报错（换搜索引擎解决不了截断，不重试）。"""
    choices = data.get("choices") or []
    if not choices:
        fail(f"响应里没有 choices（拿到字段：{sorted(data.keys())}），无法取到回答内容")

    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")

    # 完整性的判据是 finish_reason，不是 content 是否为空：
    # 思考 token 吃光预算时 content 为空串、finish_reason=length。
    if finish_reason == "length":
        fail(
            "答案不完整：生成达到 max_tokens 上限被截断（finish_reason=length）。"
            "本脚本已给足 8192 token 预算仍被截断，请调大 MAX_TOKENS 后重跑。"
        )
    if finish_reason != "stop":
        fail(f"答案不完整：finish_reason={finish_reason}（stop 才代表正常收尾），不输出半截结果")
    if not content:
        fail("答案不完整：finish_reason=stop 但 content 为空串，请重跑；持续如此请核对模型与参数")
    return content


def collect_links(data: dict) -> list:
    """从响应顶层 web_search 数组提取去重后的 http 链接条目。"""
    items = data.get("web_search")
    if not isinstance(items, list):
        return []
    links, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if link.startswith("http") and link not in seen:
            seen.add(link)
            links.append({"title": str(item.get("title") or "").strip() or "(无标题)",
                          "media": str(item.get("media") or "").strip(),
                          "link": link})
    return links


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置（或为空），无法调用智谱 API。"
             "请先执行：export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>")

    # 主引擎拿不到足够链接时换兜底引擎再试一次；答案不完整则在 check_answer_complete 里直接报错
    diagnostics = []
    for engine in SEARCH_ENGINES:
        data = chat_once(api_key, engine)
        content = check_answer_complete(data)
        links = collect_links(data)
        if len(links) >= MIN_LINKS:
            print(f"【问题】{QUESTION}\n")
            print(content)
            print("\n" + "=" * 60)
            print(f"来源链接（人工复核用，共 {len(links)} 条）：")
            for i, item in enumerate(links, 1):
                media = f"{item['media']}｜" if item["media"] else ""
                print(f"[{i}] {media}{item['title']}\n    {item['link']}")
            return
        raw_items = data.get("web_search")
        if not isinstance(raw_items, list):
            diagnostics.append(f"{engine}：响应中未出现 web_search 引用数组（可能未执行搜索）")
        else:
            diagnostics.append(
                f"{engine}：返回 {len(raw_items)} 条来源，其中 http 开头的仅 {len(links)} 条"
            )

    fail(
        f"未拿到至少 {MIN_LINKS} 条可点击的来源链接，不输出无出处的结果。各引擎情况："
        + "；".join(diagnostics)
        + "。常见原因是所用 Key/引擎组合不返回真实链接（search_std/search_pro 的 link 恒为空串），"
          "请确认使用标准 API Key，或稍后重跑。"
    )


if __name__ == "__main__":
    main()
