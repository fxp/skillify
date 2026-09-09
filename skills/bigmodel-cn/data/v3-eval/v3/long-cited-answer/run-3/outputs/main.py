#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台的联网搜索能力回答：2026 年中国新能源汽车出口的主要目的地国家有哪些。

两条硬性要求，满足才输出，否则明确报错退出（不糊弄）：
1. 答案必须完整：finish_reason 必须是 "stop"。若为 "length"（思考 token 计入
   max_tokens，预算被推理吃掉导致正文截断），自动翻倍 max_tokens 重试；
   三档预算用尽仍截断则报错退出。
2. 必须附 >= 2 条 http 开头的真实来源链接：链接取自响应体顶层 web_search 数组，
   该数组只有显式传 web_search.search_result: true 才会出现；且 search_engine
   必须选返回非空 link 的引擎（search_std / search_pro 的 link 恒为空串）。
   链接不足时依次换引擎重跑，三个引擎全失败才报错退出。

API Key 从环境变量 ZHIPUAI_API_KEY 读取，仅依赖 requests。
用法：python3 main.py
退出码：0 成功；1 配置/网络/接口错误；2 答案不完整；3 来源链接不足。
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = (
    "2026年中国新能源汽车出口的主要目的地国家有哪些？"
    "请基于联网搜索到的最新资料回答：列出主要目的地国家，简述对各国出口的大致情况"
    "（如规模、增速、主力车型或品牌），并注明数据口径（如统计时段、是否含乘用车/商用车）。"
)

MIN_LINKS = 2  # 至少 2 条可点击来源
# 思考 token 计入 max_tokens（glm-5.3 在标准端点强制思考，关不掉），预算从宽、逐档翻倍
MAX_TOKENS_LADDER = [8192, 16384, 32768]
# 实测只有这几个引擎返回非空 link，按稳定度排序轮换；不要用 search_std / search_pro
SEARCH_ENGINES = ["search_pro_bing", "search_pro_quark", "search_pro_sogou"]
REQUEST_TIMEOUT = 180  # 联网搜索 + 强制思考，单次耗时较长


def die(msg, code):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(code)


def build_payload(engine, max_tokens):
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "max_tokens": max_tokens,
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    # 引擎决定 link 是否非空；search_result:true 决定响应里是否带 web_search 数组，
                    # 两者缺一个，"可点击来源"就静默拿不到
                    "search_engine": engine,
                    "search_result": True,
                    "count": 10,
                    "content_size": "high",
                },
            }
        ],
    }


def call_once(session, api_key, engine, max_tokens):
    """单次调用，返回完整响应体 dict；失败抛 RuntimeError（带平台错误码）。"""
    try:
        resp = session.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=build_payload(engine, max_tokens),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"网络请求失败: {exc}")

    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok or "error" in body:  # 平台错误一般是 4xx + body.error，个别情况 200 也带
        err = body.get("error") or {}
        raise RuntimeError(
            f"接口报错 HTTP {resp.status_code}"
            f" code={err.get('code', '?')} message={err.get('message') or resp.text[:200]}"
        )

    if not body.get("choices"):
        raise RuntimeError(f"响应里没有 choices：{str(body)[:300]}")

    # 同步端点一般不换模型，但回显成完全不同的模型意味着计费与能力都变了，拒绝采用
    echoed = body.get("model") or ""
    if echoed and not echoed.startswith(MODEL):
        raise RuntimeError(
            f"端点把模型静默换成了 {echoed}（请求的是 {MODEL}），结果不可信，放弃"
        )
    return body


def extract_links(body):
    """从顶层 web_search 数组提取去重后的可点击链接（http/https 开头）。"""
    links, seen = [], set()
    for item in body.get("web_search") or []:
        link = (item.get("link") or "").strip()
        if link.startswith("http") and link not in seen:
            seen.add(link)
            links.append(
                {
                    "title": (item.get("title") or "").strip() or "(无标题)",
                    "media": (item.get("media") or "").strip(),
                    "link": link,
                }
            )
    return links


def answer_with_engine(session, api_key, engine):
    """一个引擎的完整尝试（内含截断重试阶梯）。返回 (answer, links, failure_reasons)。

    answer 为 None 表示三档预算用尽仍未拿到完整答案。
    接口级错误向上抛 RuntimeError，由调用方换引擎。
    """
    failures = []
    for max_tokens in MAX_TOKENS_LADDER:
        body = call_once(session, api_key, engine, max_tokens)
        choice = body["choices"][0]
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason")

        if finish_reason == "length":
            # 正文被截断（或被思考吃成空串）：判据是 finish_reason，不是空串本身。
            # 不报错退出，翻倍预算重试
            failures.append(f"max_tokens={max_tokens} 时 finish_reason=length（答案被截断）")
            continue
        if finish_reason != "stop":
            failures.append(f"finish_reason={finish_reason!r}（非 stop），放弃本次结果")
            continue
        if not answer:
            failures.append("finish_reason=stop 但 content 为空串")
            continue
        return answer, extract_links(body), failures
    return None, [], failures


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die(
            "环境变量 ZHIPUAI_API_KEY 未设置或为空。"
            "请先执行：export ZHIPUAI_API_KEY=<你的智谱开放平台 API Key>",
            1,
        )

    session = requests.Session()
    attempts = []  # 每个引擎的结局，全失败时原样汇报给用户
    last_complete_answer = None  # 记住"答案完整但链接不足"的最好结果，便于报错时说明

    for engine in SEARCH_ENGINES:
        try:
            answer, links, failures = answer_with_engine(session, api_key, engine)
        except RuntimeError as exc:
            attempts.append(f"引擎 {engine}：{exc}")
            continue

        if answer is not None and len(links) >= MIN_LINKS:
            print(answer)
            print()
            print(f"—— 来源链接（{len(links)} 条，供人工复核）——")
            for i, s in enumerate(links, 1):
                media = f"{s['media']}｜" if s["media"] else ""
                print(f"{i}. {s['title']}（{media}）")
                print(f"   {s['link']}")
            if failures:  # 靠加预算/换引擎救回来的过程，打给 stderr 备查
                print(f"[提示] {engine} 重试过程：{'；'.join(failures)}", file=sys.stderr)
            return 0

        if answer is None:
            attempts.append(f"引擎 {engine}：三档 max_tokens 用尽仍被截断（{'；'.join(failures)}）")
        else:
            last_complete_answer = (answer, links, engine)
            attempts.append(
                f"引擎 {engine}：答案完整，但可用来源链接仅 {len(links)} 条（要求 >= {MIN_LINKS}），换引擎重跑"
            )

    # 走到这里说明三个引擎都没同时满足"完整 + 带链接"
    detail = "\n".join(f"  - {a}" for a in attempts)
    if last_complete_answer is not None:
        die(
            "答案可以生成且完整，但三个搜索引擎都没返回足量的可点击来源链接，"
            f"不满足\"至少 {MIN_LINKS} 条 http 链接供人工复核\"的要求，拒绝输出半合规结果。\n"
            f"各引擎尝试结果：\n{detail}\n"
            "可能原因：search_engine 对应的搜索源暂不可用，或平台侧未返回 link 字段。",
            3,
        )
    die(
        "未能生成完整答案（所有尝试均被截断或失败），拒绝输出半截内容。\n"
        f"各引擎尝试结果：\n{detail}",
        2,
    )


if __name__ == "__main__":
    sys.exit(main())
