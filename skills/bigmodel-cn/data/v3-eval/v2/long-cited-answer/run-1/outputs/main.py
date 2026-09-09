#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台（bigmodel.cn）GLM 的联网搜索能力回答：
2026 年中国新能源汽车出口的主要目的地国家有哪些？

两条硬性验收标准及本脚本的保障方式：
1. 答案必须完整、不能截断：
   - 判据用 finish_reason == "stop"（API 自己的截断信号），而不是"内容非空"；
   - glm-5.3 思考 token 计入 max_tokens，预算给足 16384；
   - 万一仍因 length 截断，自动追加"继续"一轮；补写后仍未 stop 则明确报错。
2. 必须附 >= 2 条可点击来源链接（http 开头的真实网址）：
   - 显式传 web_search.search_result = true，否则响应体顶层不会出现 web_search
     引用数组（搜索照跑、答案照给，只是没出处，典型的静默失效）；
   - search_engine 只能选 link 非空的引擎：search_std / search_pro 的 link 恒为
     空字符串，因此依次尝试 search_pro_bing -> search_pro_quark -> search_pro_sogou；
   - 逐条过滤 http/https 开头、去空去重后不足 2 条即视为失败，换引擎重试，
     全部失败则明确报错说明原因。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
用法：ZHIPUAI_API_KEY=你的Key python3 main.py
"""

import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
MAX_TOKENS = 16384        # 思考 token 计入 max_tokens，给足预算避免 finish_reason=length
REQUEST_TIMEOUT = 180     # 联网搜索 + 思考可能较慢
MAX_CONTINUE_ROUNDS = 3   # 含首轮；finish_reason=length 时自动补写的最大轮数
MIN_SOURCES = 2

# 只有这些引擎返回的来源带真实 link（search_std / search_pro 的 link 恒为空串）
SEARCH_ENGINES = ("search_pro_bing", "search_pro_quark", "search_pro_sogou")

QUESTION = (
    "2026 年中国新能源汽车出口的主要目的地国家有哪些？"
    "请基于联网搜索到的最新公开信息回答，要求："
    "1) 按重要程度列出主要目的地国家，并尽量给出各自的出口规模、增速或代表性事件；"
    "2) 注明数据的时间范围和口径；"
    "3) 用中文分点作答，结构完整，最后给一句总结；"
    "4) 一定要把话说完，不要中途截断。"
)


def die(msg):
    print("\n[失败] " + msg, file=sys.stderr)
    sys.exit(1)


def call_chat(api_key, messages, tools=None):
    """发起一次同步 chat/completions 请求，任何失败都抛 RuntimeError 并带原因。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,      # 显式关闭流式，避免拿到 SSE 解析失败
        "max_tokens": MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError("网络请求失败：" + str(exc))

    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(
            "HTTP %d，响应不是 JSON：%s" % (resp.status_code, resp.text[:300])
        )

    if resp.status_code != 200:
        err = data.get("error") or {}
        raise RuntimeError(
            "HTTP %d，错误码 %s：%s"
            % (resp.status_code, err.get("code", "未知"),
               err.get("message", resp.text[:300]))
        )
    if not data.get("choices"):
        raise RuntimeError("响应中没有 choices：" + str(data)[:300])
    return data


def get_answer_and_sources(api_key, engine):
    """用指定搜索引擎完成一次带联网搜索的问答。

    返回 (完整回答文本, web_search 引用数组原始项)。任一步不满足
    "答案完整"都抛 RuntimeError，由上层换引擎或最终报错，绝不吞掉。
    """
    messages = [{"role": "user", "content": QUESTION}]
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": engine,   # 显式指定，不依赖未文档化的默认引擎
            "search_result": True,     # 不传 true 响应里根本没有 web_search 引用数组
            "count": 10,
            "search_recency_filter": "oneYear",
            "content_size": "high",
        },
    }]

    full_content = ""
    for round_no in range(MAX_CONTINUE_ROUNDS):
        data = call_chat(api_key, messages, tools if round_no == 0 else None)
        choice = data["choices"][0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")

        if finish_reason == "stop":
            full_content += content
            if not full_content.strip():
                raise RuntimeError("finish_reason=stop 但模型返回了空内容，回答不可用")
            return full_content, data.get("web_search") or []

        if finish_reason == "length":
            # 输出被 max_tokens 截断：回填已生成内容，追加一轮"继续"
            full_content += content
            messages = messages + [
                {"role": "assistant", "content": content or ""},
                {"role": "user",
                 "content": "输出因长度限制被截断了。请从中断处继续写完，不要重复已输出的内容。"},
            ]
            continue

        # sensitive（内容拦截）/ network_error（推理异常）等，回答不可用
        raise RuntimeError(
            "finish_reason=%s（非 stop/length），回答不可用。"
            "常见取值：stop 正常结束 / length 截断 / sensitive 内容拦截 / "
            "network_error 推理异常" % finish_reason
        )

    raise RuntimeError(
        "补写 %d 轮后 finish_reason 仍为 length，无法保证答案完整"
        % MAX_CONTINUE_ROUNDS
    )


def extract_sources(web_search_items):
    """从 web_search 引用数组里过滤出真正可点击的链接。

    只收 http:// 或 https:// 开头、非空的 link，按 URL 去重，保持原有顺序。
    """
    seen = set()
    sources = []
    for item in web_search_items:
        link = str(item.get("link") or "").strip()
        if not (link.startswith("http://") or link.startswith("https://")):
            continue
        if link in seen:
            continue
        seen.add(link)
        sources.append({
            "title": str(item.get("title") or "").strip() or "(无标题)",
            "media": str(item.get("media") or "").strip(),
            "link": link,
        })
    return sources


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("环境变量 ZHIPUAI_API_KEY 未设置（或为空）。"
            "请先执行：export ZHIPUAI_API_KEY=你的Key")

    failures = []
    for engine in SEARCH_ENGINES:
        try:
            answer, raw_items = get_answer_and_sources(api_key, engine)
        except RuntimeError as exc:
            failures.append(engine + ": " + str(exc))
            continue

        sources = extract_sources(raw_items)
        if len(sources) < MIN_SOURCES:
            failures.append(
                "%s: 回答完整，但过滤后可点击来源只有 %d 条（要求 >= %d）。"
                "该引擎本次返回的 web_search 引用中没有足够的真实链接。"
                % (engine, len(sources), MIN_SOURCES)
            )
            continue

        # finish_reason=stop 是权威的完整性判据；末尾句读只作软性提醒
        if answer.rstrip()[-1:] not in "。！？.!?)）]】”\"'":
            print("[警告] 回答末尾不是常规句读，建议人工确认内容是否完整。",
                  file=sys.stderr)

        print(answer)
        print()
        print("=" * 60)
        print("参考来源（共 %d 条，可点击，供人工复核）：" % len(sources))
        for i, s in enumerate(sources, 1):
            media = ("（%s）" % s["media"]) if s["media"] else ""
            print("%d. %s%s" % (i, s["title"], media))
            print("   " + s["link"])
        return

    die("依次尝试了搜索引擎 " + "、".join(SEARCH_ENGINES) +
        "，均未同时满足「答案完整 + 至少 %d 条可点击来源」：\n  - " % MIN_SOURCES +
        "\n  - ".join(failures) +
        "\n请检查 API Key 权限与余额、网络连通性，或稍后重试。")


if __name__ == "__main__":
    main()
