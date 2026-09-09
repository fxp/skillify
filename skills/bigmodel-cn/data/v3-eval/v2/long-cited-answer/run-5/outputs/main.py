#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 AI 开放平台的「联网搜索 + 对话补全」回答：

    2026 年中国新能源汽车出口的主要目的地国家有哪些？

硬性交付标准（不满足就明确报错退出，绝不输出半成品）：
1. 答案完整：finish_reason 必须是 "stop"。glm-5.3 在标准端点强制开启思考，
   且思考 token 计入 max_tokens，预算不足会 finish_reason=length 导致正文
   被截断甚至为空——因此给足预算，一旦截断自动翻倍重试，仍截断则报错。
2. 至少 2 条可点击来源链接：只认响应顶层 web_search 数组里 link 非空且以
   http 开头的真实网址。注意智谱的 search_std / search_pro 返回的来源
   link 恒为空字符串（HTTP 200、条数正常的静默失效），只有
   search_pro_bing / search_pro_jina / search_pro_quark / search_pro_sogou
   才带真实链接——所以按优先级依次尝试这四个引擎，某个引擎链接不足 2 条
   就换下一个重试，全部失败则报错说明。

其他说明：
- API Key 从环境变量 ZHIPUAI_API_KEY 读取（标准 API Key，
  走 https://open.bigmodel.cn/api/paas/v4，不是 GLM Coding Plan 套餐端点）。
- 仅依赖 requests，直接 python3 main.py 运行；成功退出码 0，失败退出码 1。
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 通用旗舰：1M 上下文、128K 最大输出
QUESTION = "2026 年中国新能源汽车出口的主要目的地国家有哪些？请基于 2026 年以来的公开报道和行业数据，先给出完整的目的地国家清单，再逐个国家说明出口规模、增速或主要车型等要点，最后做一句话总结。"

# 只列会返回真实链接的引擎（search_std / search_pro 的来源 link 恒为空，不在此列）。
SEARCH_ENGINES = ["search_pro_bing", "search_pro_quark", "search_pro_sogou", "search_pro_jina"]

# 思考与正文共享 max_tokens：先给足预算，截断（finish_reason=length）再翻倍重试一次。
TOKEN_BUDGETS = [16384, 65536]

MAX_TRANSIENT_RETRIES = 3  # 网络 / 429 / 5xx 的指数退避重试次数

SYSTEM_PROMPT = (
    "你是一个严谨的行业研究助理。回答必须基于联网搜索到的资料："
    "先直接给出结论（2026 年中国新能源汽车出口的主要目的地国家清单），"
    "再逐个国家给出要点（出口规模、增速、主要车型或当地布局，有数据就引用数据），"
    "最后一句话收尾总结。回答必须完整成篇，不得中途停笔，"
    "不得以“此外”“另外”之类未展开的半截话结尾。"
)


class FatalAPIError(Exception):
    """不可重试的错误（Key 无效、参数非法、内容拦截等），直接向用户报错。"""


def fail(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"[警告] {msg}", file=sys.stderr)


def call_chat(api_key, engine, max_tokens):
    """发起一次带联网搜索的对话补全，返回解析后的 JSON。

    网络 / 429 / 5xx 做指数退避重试；4xx 配置类错误重试无意义，抛 FatalAPIError。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ],
        "stream": False,  # 非流式：finish_reason 在完整响应里，便于校验是否截断
        "max_tokens": max_tokens,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    # 关键：不显式传 search_result=true，响应里根本不会出现
                    # web_search 来源数组（搜索照跑、答案照给，只是没出处）。
                    "search_result": True,
                    "count": 10,
                    "search_recency_filter": "oneYear",  # 聚焦 2026 年以来的数据
                    "content_size": "high",
                },
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_TRANSIENT_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=(15, 300))
        except requests.RequestException as exc:
            last_err = f"网络请求异常：{exc!r}"
            warn(f"{last_err}（第 {attempt}/{MAX_TRANSIENT_RETRIES} 次，退避后重试）")
            time.sleep(2 ** attempt)
            continue

        if resp.status_code < 400:
            try:
                data = resp.json()
            except ValueError:
                last_err = f"响应不是合法 JSON（HTTP {resp.status_code}）：{resp.text[:300]!r}"
                warn(f"{last_err}（第 {attempt}/{MAX_TRANSIENT_RETRIES} 次，退避后重试）")
                time.sleep(2 ** attempt)
                continue
            # 兜底：个别情况下 200 也可能带业务错误体
            if isinstance(data, dict) and "error" in data:
                err = data["error"] or {}
                raise FatalAPIError(
                    f"平台返回业务错误 code={err.get('code')} message={err.get('message')}"
                )
            return data

        body = resp.text[:500]
        if resp.status_code == 429 or resp.status_code >= 500:
            last_err = f"HTTP {resp.status_code}：{body}"
            warn(f"{last_err}（第 {attempt}/{MAX_TRANSIENT_RETRIES} 次，退避后重试）")
            time.sleep(2 ** attempt)
            continue
        # 401 Key 无效 / 400+1210 参数非法等，重试没有意义
        raise FatalAPIError(f"请求被拒绝（HTTP {resp.status_code}）：{body}")

    raise FatalAPIError(f"重试 {MAX_TRANSIENT_RETRIES} 次后仍失败，最后一次原因：{last_err}")


def extract_sources(data):
    """从响应顶层 web_search 数组提取可点击来源。

    返回 (links, total)：
    - links: link 非空且以 http:// 或 https:// 开头的来源列表（按出现顺序去重）；
    - total: web_search 数组的原始条数；若响应里根本没有这个字段则返回 None
      （说明 search_result=true 没生效，或平台没执行搜索）。
    """
    sources = data.get("web_search") if isinstance(data, dict) else None
    if not isinstance(sources, list):
        return [], None
    links, seen = [], set()
    for item in sources:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "").strip()
        if not link.lower().startswith(("http://", "https://")) or link in seen:
            continue
        seen.add(link)
        meta = " / ".join(str(x) for x in (item.get("media"), item.get("publish_date")) if x)
        links.append(
            {
                "title": str(item.get("title") or "").strip() or link,
                "url": link,
                "meta": f"（{meta}）" if meta else "",
            }
        )
    return links, len(sources)


def explain_bad_finish(finish_reason):
    reasons = {
        "sensitive": "回答触发平台内容安全拦截（finish_reason=sensitive），拿不到答案。",
        "network_error": "模型推理异常（finish_reason=network_error），拿不到答案。",
        "model_context_window_exceeded": "超出模型上下文窗口（finish_reason=model_context_window_exceeded）。",
        "tool_calls": "模型返回的是工具调用而非最终回答，非流式模式下不应出现。",
    }
    return reasons.get(finish_reason, f"异常结束状态 finish_reason={finish_reason!r}。")


def print_answer(content, links):
    print("【答案】（智谱联网搜索生成，finish_reason=stop，完整未截断，可直接贴周报）")
    print()
    print(content.strip())
    print()
    print(f"【来源链接】共 {len(links)} 条，均为 http 开头的真实网址，供人工复核：")
    for i, item in enumerate(links, 1):
        print(f"[{i}] {item['title']}{item['meta']}")
        print(f"    {item['url']}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail(
            "环境变量 ZHIPUAI_API_KEY 未设置或为空，无法调用智谱 API。"
            "请先执行：export ZHIPUAI_API_KEY=<你的标准 API Key>（注意 GLM Coding Plan "
            "套餐 Key 不能用于本脚本的标准端点，会报 1113 余额不足）。"
        )

    problems = []  # 收集各引擎的失败原因，最终一起报出
    for engine in SEARCH_ENGINES:
        for max_tokens in TOKEN_BUDGETS:
            try:
                data = call_chat(api_key, engine, max_tokens)
            except FatalAPIError as exc:
                fail(f"调用智谱 API 失败（搜索引擎 {engine}，max_tokens={max_tokens}）：{exc}")

            choices = data.get("choices") or []
            if not choices:
                fail(f"响应里没有 choices（搜索引擎 {engine}）：{str(data)[:300]}")
            choice = choices[0] or {}
            finish_reason = choice.get("finish_reason")
            content = str((choice.get("message") or {}).get("content") or "").strip()

            if finish_reason == "length":
                # 思考 token 计入 max_tokens：预算耗尽 → 正文被截断甚至为空
                problems.append(
                    f"{engine}：max_tokens={max_tokens} 时答案被截断（finish_reason=length）"
                )
                if max_tokens != TOKEN_BUDGETS[-1]:
                    warn(f"{engine} 答案被截断（finish_reason=length），加大 token 预算重试。")
                    continue
                warn(f"{engine} 答案在最大预算 {TOKEN_BUDGETS[-1]} 下仍被截断，换引擎重试。")
                break  # 换引擎重新生成一次（新采样可能更精简）

            if finish_reason != "stop":
                # sensitive / network_error / model_context_window_exceeded 等：换引擎也救不了
                fail(f"答案不完整，无法交付：{explain_bad_finish(finish_reason)}")

            if not content:
                fail(
                    f"finish_reason=stop 但正文为空（搜索引擎 {engine}，"
                    f"常见于思考用尽 token 预算），视为不完整，不输出半成品。"
                )

            # 答案已确认完整，下面校验来源链接
            links, total = extract_sources(data)
            if len(links) >= 2:
                print_answer(content, links)
                return
            if total is None:
                detail = "响应里没有出现 web_search 来源数组（search_result=true 未生效或未执行搜索）"
            else:
                detail = (
                    f"web_search 数组共 {total} 条，其中 link 非空且 http 开头的仅 "
                    f"{len(links)} 条（其余 link 为空字符串）"
                )
            problems.append(f"{engine}：答案完整但来源链接不足 2 条——{detail}")
            warn(f"{engine} 来源链接不足 2 条（{detail}），换下一个搜索引擎重试。")
            break  # 链接问题换引擎才有意义，跳出预算循环

    fail(
        "无法满足交付标准，不输出半成品。已尝试的搜索引擎与失败原因：\n  - "
        + "\n  - ".join(problems)
        + "\n提示：智谱 search_std/search_pro 引擎返回的来源 link 恒为空，本脚本已只使用会返回"
        "真实链接的四个引擎（bing/quark/sogou/jina）。若全部引擎链接仍不足 2 条，多为平台侧"
        "搜索源临时异常，请稍后重试；若答案反复被截断，可调大脚本里的 TOKEN_BUDGETS。"
    )


if __name__ == "__main__":
    main()
