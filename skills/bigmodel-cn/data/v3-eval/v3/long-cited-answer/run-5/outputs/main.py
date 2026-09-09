#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用智谱开放平台（bigmodel.cn）GLM 的联网搜索能力回答：
    「2026 年中国新能源汽车出口的主要目的地国家有哪些」

两条硬性要求，不满足就明确报错退出，绝不输出半截结果：
1. 答案必须完整：finish_reason 必须是 stop。若为 length（输出被 max_tokens 截断，
   注意思考 token 也计入预算），自动放大预算重试；仍不行才报错。
2. 至少 2 条可点击的 http(s) 来源链接：实测只有 search_pro_bing / search_pro_quark /
   search_pro_sogou / search_pro_jina 会返回非空 link（search_std / search_pro 的
   link 恒为空串），且必须显式传 web_search.search_result=true，响应里才会出现
   来源数组。某引擎链接不足时自动换下一个引擎重跑。

运行方式：ZHIPUAI_API_KEY=你的Key python3 main.py
依赖：仅 requests。
"""

import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
QUESTION = (
    "2026年中国新能源汽车出口的主要目的地国家有哪些？"
    "请基于联网搜索到的最新资料，按重要程度列出主要目的地国家，"
    "并为每个国家附上简要依据（如出口量、同比增速、市场份额等数据），"
    "最后做一个小结。回答要完整，不要中途停止。"
)

# 实测会返回真实链接的引擎，按优先级排列。不要换成 search_std / search_pro（link 恒为空串）
SEARCH_ENGINES = ("search_pro_bing", "search_pro_quark", "search_pro_sogou", "search_pro_jina")
# finish_reason=length 时按此梯度放大输出预算（上限 131072）
MAX_TOKENS_LADDER = (8192, 24576, 65536)
MIN_LINKS = 2
HTTP_TIMEOUT = 300   # 联网搜索 + 生成较慢，给足超时
NET_RETRIES = 3      # 网络层（超时/连接失败）重试次数


def die(msg):
    """明确报错退出：说清原因，不输出半截结果糊弄。"""
    print("\n[失败] " + msg, file=sys.stderr)
    sys.exit(1)


def post_chat(api_key, engine, max_tokens):
    """带 web_search 工具调一次 chat/completions，返回原始响应 dict。只抛请求层错误。"""
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [{
            "type": "web_search",
            "web_search": {
                "enable": True,
                "search_engine": engine,              # 决定来源 link 是否非空
                "search_result": True,                # 不显式传 true，响应里没有来源数组
                "count": 10,
                "search_recency_filter": "oneYear",   # 2026 年的数据需要最新资讯
                "content_size": "high",
            },
        }],
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}

    last_err = None
    for attempt in range(1, NET_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
            body = resp.json() if resp.content else {}
            # 业务错误可能随 4xx 返回，也可能 200 带 error 字段，统一拆出来
            err = body.get("error")
            if err:
                raise RuntimeError("API 返回错误 code=%s message=%s" % (err.get("code"), err.get("message")))
            if resp.status_code >= 400:
                raise RuntimeError("HTTP %d: %s" % (resp.status_code, resp.text[:300]))
            return body
        except (requests.Timeout, requests.ConnectionError, ValueError) as e:
            last_err = e
            time.sleep(2 * attempt)   # 退避后重试
    raise RuntimeError("连续 %d 次请求失败：%s" % (NET_RETRIES, last_err))


def collect_links(body):
    """从响应抽出去重后的可点击来源（仅保留 http/https 开头的真实链接）。"""
    raw = body.get("web_search")
    if not raw:   # 兜底：个别版本把来源数组挂在 message 里
        choices = body.get("choices") or [{}]
        raw = (choices[0].get("message") or {}).get("web_search") or []
    seen, links = set(), []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        links.append({
            "url": url,
            "title": str(item.get("title") or "").strip() or "(未提供标题)",
            "media": str(item.get("media") or "").strip(),
            "date": str(item.get("publish_date") or "").strip(),
        })
    return links


def report(content, links, engine):
    """输出最终结果：完整答案 + 可点击来源列表。"""
    print("=" * 24 + " 答案 " + "=" * 24)
    print(content.strip())
    print()
    print("=" * 20 + " 来源链接（人工复核用）" + "=" * 20)
    for i, s in enumerate(links, 1):
        meta = "，".join(x for x in (s["media"], s["date"]) if x)
        print("[%d] %s" % (i, s["title"]))
        print("    %s%s" % (s["url"], ("（%s）" % meta) if meta else ""))
    print()
    print("[信息] 搜索引擎=%s，来源 %d 条（满足 ≥%d 条要求）"
          % (engine, len(links), MIN_LINKS), file=sys.stderr)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("环境变量 ZHIPUAI_API_KEY 未设置或为空。请先执行 "
            "export ZHIPUAI_API_KEY=<你的智谱开放平台Key> 再运行本脚本。")

    problems = []   # 记录每次尝试的失败原因，最终汇总报错用
    for engine in SEARCH_ENGINES:
        for max_tokens in MAX_TOKENS_LADDER:
            print("[运行] 引擎=%s max_tokens=%d …" % (engine, max_tokens), file=sys.stderr)
            try:
                body = post_chat(api_key, engine, max_tokens)
            except RuntimeError as e:
                problems.append("%s: 请求失败（%s）" % (engine, e))
                break   # 参数/权限类错误重试无意义，换引擎

            choices = body.get("choices") or []
            if not choices:
                problems.append("%s: 响应里没有 choices" % engine)
                break
            finish_reason = choices[0].get("finish_reason")
            content = str((choices[0].get("message") or {}).get("content") or "")

            # 完整性校验：length=被 max_tokens 截断；内容为空多半也是预算被思考 token 吃光
            if finish_reason == "length" or not content.strip():
                problems.append("%s@max_tokens=%d: 答案不完整（finish_reason=%s，内容 %d 字）"
                                % (engine, max_tokens, finish_reason, len(content)))
                continue   # 放大预算重试
            if finish_reason != "stop":
                problems.append("%s: finish_reason=%s，非正常结束（如 sensitive/network_error）"
                                % (engine, finish_reason))
                break

            # 完整性通过，再校验来源链接
            links = collect_links(body)
            if len(links) >= MIN_LINKS:
                echo_model = str(body.get("model") or "")
                if echo_model and echo_model.lower() != MODEL:
                    print("[警告] 平台回显模型为 %s，与请求的 %s 不一致，请注意核对。"
                          % (echo_model, MODEL), file=sys.stderr)
                report(content, links, engine)
                return
            problems.append("%s: 答案完整但仅拿到 %d 条 http 来源链接（需 ≥%d），换引擎重试"
                            % (engine, len(links), MIN_LINKS))
            break   # 链接不够（该引擎 link 为空或来源太少），换引擎

    die("无法同时满足『答案完整』与『≥%d 条可点击来源链接』，已尝试的所有组合均失败：\n  - %s\n"
        "常见原因：① Key 无联网搜索权限或欠费（如错误码 1113）；② 所用搜索引擎未返回可点击链接"
        "（search_std/search_pro 的 link 恒为空）；③ 输出预算被思考 token 耗尽导致截断。"
        "请核对 Key 权限与平台控制台后再试。"
        % (MIN_LINKS, "\n  - ".join(problems)))


if __name__ == "__main__":
    main()
