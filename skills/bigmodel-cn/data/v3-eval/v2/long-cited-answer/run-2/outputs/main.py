#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 AI（bigmodel.cn）联网搜索回答：2026 年中国新能源汽车出口的主要目的地国家有哪些。

产出可直接贴进周报，两条硬性校验，任一不满足即以退出码 1 报错退出，绝不输出半成品：
  1. 答案完整：finish_reason 必须为 stop、正文非空、以句末标点收尾；
     若 finish_reason == length（输出被 max_tokens 截断）则自动加倍预算重试，仍失败则报错。
  2. 来源可核：响应顶层 web_search 引用数组中至少 2 条非空、可解析的 http(s) 链接；
     不足时按降级链更换仍返回真实链接的搜索引擎重试，全部失败则报错。

依赖：仅 requests（pip install requests）。运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import os
import sys
from urllib.parse import urlparse

import requests

CHAT_COMPLETIONS_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 标准端点同步接口，不会被静默换模型

QUESTION = (
    "2026年中国新能源汽车出口的主要目的地国家有哪些？"
    "请先给总体结论，再分条列出主要目的地国家，附出口量、增速或排名等依据，"
    "并注明数据的时间范围与统计口径。"
)

SYSTEM_PROMPT = (
    "你是一个严谨的行业研究员，请基于联网搜索结果回答用户问题：\n"
    "1. 先用两三句话给出总体结论；\n"
    "2. 再分条列出主要目的地国家，附出口量/增速/排名等数据依据，注明时间范围与统计口径；\n"
    "3. 搜索结果之间数据有冲突时如实说明，不得编造来源；\n"
    "4. 回答必须完整自包含，最后一句是完整的总结句并以句号结尾，严禁中途截断。"
)

# 只有这几个引擎返回的来源带真实 link。search_std / search_pro 的 link 恒为空字符串
# （HTTP 200、条数正常、只有链接是空的，典型静默失效），需要可点击来源时绝不能用。
SEARCH_ENGINES = [
    "search_pro_sogou",  # 官方参数表在列，实测带链接
    "search_pro_quark",  # 官方参数表在列，实测带链接
    "search_pro_bing",   # 未列入官方参数表，但实测可用且带链接
]

MIN_LINKS = 2          # 至少 2 条可点击来源
MAX_OUTPUT_ATTEMPTS = 3  # 截断重试次数，max_tokens 起步 16384、逐次翻倍（glm-5.3 上限 131072）
INITIAL_MAX_TOKENS = 16384
REQUEST_TIMEOUT = (10, 300)  # 连接 10s / 读取 300s：联网搜索 + 长回答较慢

# 完整回答的合法收尾字符（句末标点及收束引号/括号等）
_CLOSING_CHARS = set('。！？!?….”"\'』」）)]:；;')


def fail(message: str) -> "NoReturn":  # noqa: F821
    """打印明确错误原因并以非零退出码结束，不输出半成品答案。"""
    print(f"[错误] {message}", file=sys.stderr)
    sys.exit(1)


def looks_finished(text: str) -> bool:
    """启发式校验回答正常收尾（配合 system prompt 的“以句号结尾”要求）。"""
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in _CLOSING_CHARS


def describe_http_error(status_code: int, body: dict) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        return f"HTTP {status_code}，平台错误码 {error.get('code')}：{error.get('message')}"
    snippet = str(body)[:300]
    return f"HTTP {status_code}，响应：{snippet}"


def call_chat(api_key: str, engine: str, max_tokens: int) -> dict:
    """调一次带 web_search 工具的同步对话补全，返回解析后的 JSON 响应体。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ],
        "tools": [
            {
                "type": "web_search",
                "web_search": {
                    "enable": True,
                    "search_engine": engine,
                    # 实测关键项：不显式传 true，响应体顶层不会出现 web_search 引用数组，
                    # 搜索照跑、答案照给，只是拿不到出处（静默失效）。
                    "search_result": True,
                    "search_intent": False,  # 问题意图明确，跳过意图识别直接搜
                    "require_search": True,  # 强制执行联网搜索
                    "count": 10,
                    "search_recency_filter": "oneYear",  # 覆盖近一年，含 2026 全年报道
                    "content_size": "high",  # 摘要更详细，供模型引用数据
                },
            }
        ],
        "max_tokens": max_tokens,
        # 思考 token 计入 max_tokens；glm-5.3 在标准端点强制思考，用 low 降低占用防挤占输出预算
        "reasoning_effort": "low",
        "stream": False,
    }
    resp = requests.post(
        CHAT_COMPLETIONS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:300]}")
    if resp.status_code != 200:
        raise RuntimeError(describe_http_error(resp.status_code, body))
    if isinstance(body.get("error"), dict):  # 部分错误 HTTP 200 也带 error 体
        raise RuntimeError(describe_http_error(resp.status_code, body))
    return body


def generate_answer(api_key: str, engine: str):
    """生成答案并校验完整性。返回 (answer, refs)；不完整时抛 RuntimeError 说明原因。

    完整性判据是 finish_reason 而不是“有没有内容”：glm-5.3 的思考 token 计入
    max_tokens，预算不足时 finish_reason=length、正文是被截断的半截话。
    """
    max_tokens = INITIAL_MAX_TOKENS
    last_problem = "未调用"
    for attempt in range(1, MAX_OUTPUT_ATTEMPTS + 1):
        body = call_chat(api_key, engine, max_tokens)
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(f"响应中没有 choices 字段：{str(body)[:300]}")
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        refs = body.get("web_search") or []

        if finish_reason == "length":
            last_problem = f"finish_reason=length：输出达到 max_tokens={max_tokens} 被截断（第 {attempt} 次尝试）"
            max_tokens *= 2  # 加倍预算重试
            continue
        if finish_reason in ("sensitive", "network_error", "model_context_window_exceeded"):
            raise RuntimeError(
                f"模型未正常完成，finish_reason={finish_reason}（换搜索引擎无法解决，已终止）"
            )
        if finish_reason != "stop":
            raise RuntimeError(f"异常 finish_reason={finish_reason!r}，无法确认答案完整")
        if not answer:
            last_problem = f"finish_reason=stop 但 content 为空（第 {attempt} 次尝试）"
            max_tokens *= 2
            continue
        if not looks_finished(answer):
            last_problem = (
                f"finish_reason=stop 但答案疑似未收尾，末字符为 {answer[-1]!r}（第 {attempt} 次尝试）"
            )
            continue  # 再生成一次，system prompt 已要求以句号结尾
        return answer, refs
    raise RuntimeError(
        f"经 {MAX_OUTPUT_ATTEMPTS} 次尝试答案仍不完整，最后问题：{last_problem}。"
        "不输出半截答案（周报场景要求完整）"
    )


def extract_clickable_links(refs) -> list:
    """从 web_search 引用数组提取去重后的真实可点击链接。

    只认 scheme 为 http/https 且带主机名的 URL；引擎返回空 link 的条目（如
    search_std/search_pro 的已知行为）会被直接过滤掉。
    """
    links, seen = [], set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        link = (ref.get("link") or "").strip()
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        if link in seen:
            continue
        seen.add(link)
        links.append(
            {
                "title": (ref.get("title") or "").strip() or "(无标题)",
                "link": link,
                "media": (ref.get("media") or "").strip(),
                "publish_date": (ref.get("publish_date") or "").strip(),
            }
        )
    return links


def print_result(answer: str, links: list) -> None:
    bar = "=" * 64
    print(bar)
    print("2026 年中国新能源汽车出口主要目的地国家（智谱 GLM 联网搜索）")
    print(bar)
    print(answer)
    print()
    print(f"来源链接（供人工复核，共 {len(links)} 条，均以 http 开头）：")
    for i, item in enumerate(links, 1):
        meta = "，".join(x for x in (item["media"], item["publish_date"]) if x)
        suffix = f"（{meta}）" if meta else ""
        print(f"  {i}. {item['title']}{suffix}")
        print(f"     {item['link']}")
    print()
    print(
        f"[校验通过] 答案完整（finish_reason=stop 且正常收尾）；"
        f"可点击来源 {len(links)} 条（要求 ≥ {MIN_LINKS}）。"
    )


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        fail("环境变量 ZHIPUAI_API_KEY 未设置或为空。请先执行：export ZHIPUAI_API_KEY=<你的 Key>"
             "（在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）")

    engine_reports = []
    for engine in SEARCH_ENGINES:
        try:
            answer, refs = generate_answer(api_key, engine)
        except requests.Timeout:
            fail(f"请求智谱 API 超时（读取超时 {REQUEST_TIMEOUT[1]}s）。可稍后重试。")
        except requests.RequestException as exc:
            fail(f"网络请求失败：{exc!r}")
        except RuntimeError as exc:
            fail(str(exc))  # 答案不完整 / 平台报错，换引擎无法解决，直接终止

        links = extract_clickable_links(refs)
        if len(links) >= MIN_LINKS:
            print_result(answer, links)
            return
        engine_reports.append(
            f"  - {engine}：返回引用 {len(refs)} 条，其中可点击链接 {len(links)} 条"
        )
        # 链接不足与答案质量无关，属于该引擎的返回问题，换降级链里的下一个引擎重试

    fail(
        "所有候选搜索引擎均未返回足够的可点击来源链接（要求 ≥ "
        f"{MIN_LINKS} 条），不输出无出处的答案。各引擎结果：\n" + "\n".join(engine_reports)
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):  # 防止 Windows 终端中文乱码
        sys.stdout.reconfigure(encoding="utf-8")
    main()
