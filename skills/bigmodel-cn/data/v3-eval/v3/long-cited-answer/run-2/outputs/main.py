#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱开放平台（bigmodel.cn）的联网搜索能力回答：

    「2026 年中国新能源汽车出口的主要目的地国家有哪些」

流程（两段式，保证来源链接真实、答案完整）：
  1. POST /paas/v4/web_search 拿带真实链接的搜索结果。
     注意：实测 search_std / search_pro 两个引擎返回的 link 恒为空串，
     只有 search_pro_bing / _jina / _quark / _sogou 才带可点击链接，
     所以这里用 search_pro_bing，异常时依次降级 _quark / _sogou。
  2. 把搜索结果拼进 prompt，POST /paas/v4/chat/completions（glm-5.3）生成答案。
     glm-5.3 在标准端点思考强制开启且思考 token 计入 max_tokens，预算给足；
     finish_reason == "length"（被截断）时自动翻倍 max_tokens 重试。
  3. 硬校验：答案必须完整（finish_reason == "stop" 且非空不过短）、
     至少 2 条 http(s) 开头的来源链接；任一不满足则明确报错退出，
     绝不把半截结果当成功输出。

运行：python3 main.py
依赖：仅 requests；API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import os
import re
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
CHAT_URL = API_BASE + "/chat/completions"
WEB_SEARCH_URL = API_BASE + "/web_search"

MODEL = "glm-5.3"
QUESTION = "2026年中国新能源汽车出口主要目的地国家有哪些"

# 实测只有这些引擎的 link 非空（search_std / search_pro 恒为空串，不能用）
SEARCH_ENGINES = ("search_pro_bing", "search_pro_quark", "search_pro_sogou")

MIN_SOURCES = 2           # 硬性要求：至少 2 条可点击来源
MAX_SOURCES_LISTED = 6    # 答案后附带的来源条数上限
INIT_MAX_TOKENS = 8192    # 思考 token 计入 max_tokens，起步就给足
MAX_TOKENS_CEILING = 131072
MIN_ANSWER_CHARS = 80     # 低于此长度视为未正常作答
MAX_CHAT_ATTEMPTS = 4

SEARCH_TIMEOUT = 30       # 秒
CHAT_TIMEOUT = 300        # 秒（思考模式 + 长输出，放宽）


def warn(msg):
    print(f"[提示] {msg}", file=sys.stderr, flush=True)


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def post_json(url, api_key, payload, timeout):
    """POST JSON 并做统一错误归一：网络异常 / HTTP 非 200 / body 带 error 都抛 RuntimeError。"""
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"网络请求失败：{exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = None
    # 部分错误以 HTTP 200 + body.error 返回，先判 body 再判状态码
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        raise RuntimeError(f"接口返回错误 code={err.get('code')} message={err.get('message')}")
    if resp.status_code != 200:
        text = str(body)[:300] if body is not None else resp.text[:300]
        raise RuntimeError(f"HTTP {resp.status_code}: {text}")
    if body is None:
        raise RuntimeError("响应不是合法 JSON")
    return body


def collect_sources(api_key):
    """联网搜索并收集带可点击链接的来源；单引擎失败自动换下一个，凑不齐 MIN_SOURCES 条则报错退出。"""
    sources, seen, failures = [], set(), []
    for engine in SEARCH_ENGINES:
        warn(f"调用联网搜索（引擎 {engine}）…")
        try:
            body = post_json(
                WEB_SEARCH_URL,
                api_key,
                {
                    "search_query": QUESTION,  # 该字段限长 70 字符，本问题远低于上限
                    "search_engine": engine,
                    "search_intent": False,
                    "count": 10,
                    "content_size": "high",
                },
                SEARCH_TIMEOUT,
            )
        except RuntimeError as exc:
            failures.append(f"{engine}: {exc}")
            warn(f"引擎 {engine} 调用失败，换下一个引擎重试（{exc}）")
            continue
        items = body.get("search_result") or []
        usable = 0
        for item in items:
            link = str(item.get("link") or "").strip()
            if not (link.startswith("http://") or link.startswith("https://")):
                continue  # link 为空串的结果无法人工复核，直接丢弃
            if link in seen:
                continue
            seen.add(link)
            usable += 1
            sources.append(
                {
                    "title": str(item.get("title") or "").strip() or "(无标题)",
                    "link": link,
                    "media": str(item.get("media") or "").strip(),
                    "publish_date": str(item.get("publish_date") or "").strip(),
                    "content": re.sub(r"\s+", " ", str(item.get("content") or "")).strip(),
                }
            )
        warn(f"引擎 {engine}：返回 {len(items)} 条，其中带可点击链接的 {usable} 条。")
        if len(sources) >= MIN_SOURCES:
            break
    if len(sources) < MIN_SOURCES:
        detail = "；".join(failures) if failures else "各引擎均调用成功但均无可点击链接"
        die(
            f"无法获得至少 {MIN_SOURCES} 条可点击的来源链接，拒绝输出答案。"
            f"已尝试引擎 {'、'.join(SEARCH_ENGINES)}（{detail}），"
            f"最终仅收集到 {len(sources)} 条带 http(s) 链接的来源。"
            "说明：智谱 web_search 的 search_std / search_pro 引擎返回的 link 恒为空串，"
            "本脚本已只用实测带真实链接的 bing/quark/sogou 引擎；仍拿不到说明搜索侧暂时无可用来源，"
            "请稍后重试或到 docs.bigmodel.cn 核实搜索引擎可用性。"
        )
    return sources


def build_prompt(sources):
    refs = "\n\n".join(
        f"[{i}] {s['title']}"
        + (f"（{' / '.join(x for x in (s['media'], s['publish_date']) if x)}）" if (s['media'] or s['publish_date']) else "")
        + f"\n{s['content']}"
        for i, s in enumerate(sources, 1)
    )
    return (
        f"问题：{QUESTION}\n\n"
        f"以下是联网搜索得到的资料，编号即引用序号：\n\n{refs}\n\n"
        "请依据上述资料回答问题，要求：\n"
        "1. 只依据资料内容作答，资料未覆盖的部分如实说明，不要编造数据。\n"
        "2. 用中文分点概括主要目的地国家及各自的市场规模、车型或增长特点；"
        "如资料是阶段性数据（如上半年/前 N 月），请注明数据时点。\n"
        "3. 引用资料时在相应结论句末标注编号，如 [1][3]。\n"
        "4. 不要在答案里输出任何网址（来源链接由程序统一附在答案后面）。\n"
        "5. 必须一次性写完整个答案，不要中途停笔或写「待续」。"
    )


def generate_answer(api_key, prompt):
    """调用 glm-5.3 生成答案；被截断（finish_reason=length）则翻倍 max_tokens 重试，拿不到完整答案就报错退出。"""
    max_tokens = INIT_MAX_TOKENS
    for attempt in range(1, MAX_CHAT_ATTEMPTS + 1):
        try:
            body = post_json(
                CHAT_URL,
                api_key,
                {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.6,
                },
                CHAT_TIMEOUT,
            )
        except RuntimeError as exc:
            if attempt >= MAX_CHAT_ATTEMPTS:
                die(f"调用对话接口失败（已重试 {attempt} 次）：{exc}")
            warn(f"第 {attempt} 次调用对话接口失败，重试（{exc}）")
            continue

        choices = body.get("choices") or []
        if not choices:
            die(f"对话接口响应中没有 choices，无法取答案：{str(body)[:300]}")
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        content = str((choice.get("message") or {}).get("content") or "").strip()

        # 防模型静默替换：同步端点实测不换模型，回显不一致按能力/计费风险处理
        echoed = str(body.get("model") or "").lower()
        if echoed and MODEL not in echoed:
            die(f"实际执行模型与请求不一致（请求 {MODEL}，回显 {echoed}），已中止以免能力与计费偏差。")

        if finish_reason == "stop" and len(content) >= MIN_ANSWER_CHARS:
            return content

        # 异常路径：length / sensitive / network_error / model_context_window_exceeded / 空内容 / 过短
        if finish_reason in ("sensitive", "network_error", "model_context_window_exceeded"):
            die(
                f"模型生成异常结束：finish_reason={finish_reason}"
                "（sensitive=内容安全拦截，network_error=服务端网络错误，"
                "model_context_window_exceeded=超出上下文窗口），未产出可用答案，已中止。"
            )
        if finish_reason == "length" or not content or len(content) < MIN_ANSWER_CHARS:
            if max_tokens >= MAX_TOKENS_CEILING or attempt >= MAX_CHAT_ATTEMPTS:
                die(
                    f"答案不完整，拒绝输出（finish_reason={finish_reason}，"
                    f"content 长度 {len(content)} 字符，max_tokens 已放宽到 {max_tokens}，"
                    f"重试 {attempt} 次后仍未拿到完整答案）。"
                    "本结果要贴周报，半截答案不可用，请调大 MAX_CHAT_ATTEMPTS/INIT_MAX_TOKENS 后重试。"
                )
            max_tokens = min(max_tokens * 2, MAX_TOKENS_CEILING)
            warn(
                f"第 {attempt} 次生成不完整（finish_reason={finish_reason}，"
                f"长度 {len(content)}），max_tokens 翻倍到 {max_tokens} 重试…"
            )
            continue
        die(f"未预期的结束状态：finish_reason={finish_reason}，content 长度 {len(content)}，已中止。")
    die(f"重试 {MAX_CHAT_ATTEMPTS} 次仍未得到完整答案，拒绝输出半截结果。")


def pick_sources_to_list(answer, sources):
    """优先列出答案里被 [n] 实际引用的来源，不足 MIN_SOURCES 条时按搜索排名补齐，最多列 MAX_SOURCES_LISTED 条。"""
    cited = []
    for m in re.finditer(r"\[(\d{1,3})\]", answer):
        idx = int(m.group(1))
        if 1 <= idx <= len(sources) and idx not in cited:
            cited.append(idx)
    for idx in range(1, len(sources) + 1):
        if len(cited) >= MIN_SOURCES:
            break
        if idx not in cited:
            cited.append(idx)
    return sorted(cited)[:MAX_SOURCES_LISTED]


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die(
            "缺少 API Key：环境变量 ZHIPUAI_API_KEY 未设置。"
            "请先执行 export ZHIPUAI_API_KEY=<智谱开放平台标准 API Key> 再运行。"
            "注意：GLM Coding Plan 套餐 Key 与标准 API 不通用，套餐 Key 打标准端点会报 1113。"
        )

    sources = collect_sources(api_key)
    answer = generate_answer(api_key, build_prompt(sources))
    listed = pick_sources_to_list(answer, sources)
    if len(listed) < MIN_SOURCES:
        die(f"内部校验失败：可展示来源仅 {len(listed)} 条，不足 {MIN_SOURCES} 条，拒绝输出。")

    lines = [
        f"问题：{QUESTION}",
        "",
        answer,
        "",
        f"来源链接（{len(listed)} 条，http 开头可直接点击，供人工复核）：",
    ]
    for idx in listed:
        s = sources[idx - 1]
        meta = " / ".join(x for x in (s["media"], s["publish_date"]) if x)
        lines.append(f"[{idx}] {s['title']}" + (f"（{meta}）" if meta else ""))
        lines.append(f"    {s['link']}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
