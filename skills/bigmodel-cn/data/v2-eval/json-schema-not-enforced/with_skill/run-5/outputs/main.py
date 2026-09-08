#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对一批文本做情感分类，输出严格结构化的结果供入库。

用法：
    export ZHIPUAI_API_KEY=your-key
    python3 main.py

stdout 输出（每条文本一行，顺序与 TEXTS 一致，除结果外不打印任何内容）：
    {"sentiment": "正面", "score": 0.93}

为什么客户端要做这么多兜底：
智谱 chat/completions 的 response_format 只支持 text / json_object 两种取值，
没有 json_schema 之类的强约束模式（官方文档与实测均确认）。json_object 只尽量
保证"像 JSON"，字段名和取值范围完全靠 prompt 约定，模型偶发夹带解释文字、
输出英文枚举值、带百分号的数字等。因此本脚本：
  1. 在 system prompt 里把目标结构写成硬性要求；
  2. 客户端白名单校验 + 归一化（sentiment 只认三个中文值及常见英文变体，
     score 归一到 [0,1]，越界值不猜不截断）；
  3. 校验失败带具体原因重试；
  4. 全部尝试失败则该条不出现在 stdout（宁缺毋脏），错误详情走 stderr。
"""

import json
import math
import os
import re
import sys
import time

import requests

# ----------------------------- 配置 -----------------------------

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY_ENV = "ZHIPUAI_API_KEY"

# 选 glm-5.2：支持 thinking.type=disabled 显式关闭深度思考（glm-5.3 在标准端点
# 强制思考，且思考 token 计入 max_tokens，预算小了会拿到空 content）。简单分类
# 任务关掉思考更快更省，也避开该陷阱。
MODEL = "glm-5.2"

REQUEST_OPTIONS = {
    "temperature": 0.1,                          # 分类任务要稳定，压低随机性
    "max_tokens": 1024,                          # 单个 JSON 对象绰绰有余
    "thinking": {"type": "disabled"},            # 关闭深度思考
    "response_format": {"type": "json_object"},  # 平台无 json_schema 强约束
}

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")
# 模型偶尔不守规矩输出英文枚举，映射回来，比直接判死更稳
SENTIMENT_ALIASES = {
    "正面": "正面",
    "负面": "负面",
    "中性": "中性",
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "pos": "正面",
    "neg": "负面",
}

MAX_PARSE_ATTEMPTS = 3   # 单条文本：含校验失败重试的总尝试次数
MAX_HTTP_ATTEMPTS = 3    # 网络层（超时 / 429 / 5xx）重试次数
HTTP_TIMEOUT = 60        # 秒

SYSTEM_PROMPT = (
    "你是一个严格的结构化情感分类器，输出会直接写入数据库。对用户给出的一条"
    "文本判断整体情感倾向，只输出一个 JSON 对象，除此之外不得输出任何文字、"
    "解释、前后缀或 Markdown 代码块标记。\n"
    "目标 JSON 结构（字段名和取值必须严格一致，多一个字段、少一个字段、改一个"
    "字段名都算错误）：\n"
    '{"sentiment": "正面", "score": 0.95}\n'
    "字段要求：\n"
    '1. sentiment：只能取 "正面"、"负面"、"中性" 三个中文词之一；明确褒义判为'
    "正面，明确贬义判为负面，平淡、无所谓好坏或褒贬难以判定时判为中性；禁止"
    "使用 positive/negative/neutral 等英文或任何其他取值。\n"
    "2. score：0 到 1 之间的纯数字（不加引号、不带百分号），表示分类置信度，"
    "越接近 1 越确定，越接近 0 越不确定。\n"
    "3. 整个回复必须是能被 json.loads 直接解析的合法 JSON，不得包含任何多余"
    "内容。"
)

# ----------------------------- 异常 -----------------------------


class ClassifyError(Exception):
    """单条文本分类失败（重试耗尽或不可恢复错误）。"""


# ------------------------- 输出解析与归一 -------------------------


def extract_json_object(raw):
    """从模型输出里尽力抠出一个 JSON 对象，抠不出返回 None。

    json_object 模式理论上返回纯 JSON，但实测仍可能夹带解释文字或代码块
    栅栏，所以做三层降级：直接解析 → 剥 ```json``` 栅栏 → 截取首尾大括号。
    """
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass
    return None


def normalize_sentiment(value):
    """归一 sentiment；不在合法取值（含常见英文变体）内返回 None。"""
    if isinstance(value, str):
        return SENTIMENT_ALIASES.get(value.strip().lower())
    return None


def normalize_score(value):
    """把 score 归一成 [0,1] 的 float；解释不了返回 None（交给重试）。"""
    percent = False
    if isinstance(value, bool):  # bool 是 int 子类，true/false 不是合法分数
        return None
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("%"):  # "95%" 有明确的百分比信号，换算回 [0,1]
            percent = True
            s = s[:-1].strip()
        try:
            value = float(s)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score):
        return None
    if percent:
        score /= 100.0
    if 0.0 <= score <= 1.0:
        return round(score, 4)
    return None  # 越界（如 95、-1）不猜不截断，判无效走重试


def normalize_result(data):
    """白名单化成 {"sentiment": ..., "score": ...}；非法返回 None。

    即使模型多吐了字段（reason/keywords 之类），返回的对象也恰好只有这两个
    键，保证入库结构不变。
    """
    if not isinstance(data, dict):
        return None
    sentiment = normalize_sentiment(data.get("sentiment"))
    score = normalize_score(data.get("score"))
    if sentiment is None or score is None:
        return None
    return {"sentiment": sentiment, "score": score}


# ----------------------------- 请求 -----------------------------


def post_chat(session, messages):
    """发一次对话请求（带网络层重试），返回解析后的响应 dict。"""
    payload = {"model": MODEL, "messages": messages, **REQUEST_OPTIONS}
    last_err = None
    for attempt in range(1, MAX_HTTP_ATTEMPTS + 1):
        try:
            resp = session.post(API_URL, json=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络异常 {exc!r}"
        else:
            if resp.ok:
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    raise ClassifyError(f"响应不是 JSON：{resp.text[:200]}")
                err = body.get("error")  # 防御：极少数情况 200 也携带错误体
                if err:
                    raise ClassifyError(f"接口返回错误：{err}")
                return body
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                break  # 参数/鉴权类 4xx 重试没有意义，直接失败
        if attempt < MAX_HTTP_ATTEMPTS:
            time.sleep(2 * attempt)
    raise ClassifyError(f"请求失败（共尝试 {attempt} 次）：{last_err}")


def get_content(body):
    """取出 choices[0].message.content；响应结构异常时抛 ClassifyError。"""
    choices = body.get("choices") or []
    if not choices:
        raise ClassifyError(f"响应缺少 choices：{str(body)[:200]}")
    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        content = ""
    if finish_reason not in (None, "stop"):
        # length：输出被 max_tokens 截断（思考 token 也计入该预算）；sensitive：
        # 内容安全拦截。二者都拿不到完整 JSON，先提示，重试交给上层统一处理。
        print(f"[警告] finish_reason={finish_reason}，输出可能不完整", file=sys.stderr)
    return content


# ----------------------------- 主流程 -----------------------------


def classify(session, text):
    """对单条文本做情感分类，成功返回白名单化的结果 dict。"""
    feedback = None
    for _ in range(MAX_PARSE_ATTEMPTS):
        user_content = f"待分类文本：{text}"
        if feedback:
            user_content += (
                f"\n\n你上一次的输出未通过校验：{feedback}。"
                "请严格按系统说明的目标 JSON 结构重新输出，只输出 JSON 本身。"
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        body = post_chat(session, messages)
        content = get_content(body)
        data = extract_json_object(content)
        result = normalize_result(data)
        if result is not None:
            return result

        # 构造带具体原因的反馈，下一轮让模型纠正
        if data is None:
            snippet = (content or "").strip()[:100] or "（空输出）"
            feedback = f"输出无法解析为 JSON，原始输出开头为：{snippet}"
        elif not isinstance(data, dict):
            feedback = "输出是一个 JSON 数组或标量，不是对象"
        else:
            problems = []
            if normalize_sentiment(data.get("sentiment")) is None:
                problems.append(
                    'sentiment 必须是 '
                    + "、".join(VALID_SENTIMENTS)
                    + f" 之一，实际为 {data.get('sentiment')!r}"
                )
            if normalize_score(data.get("score")) is None:
                problems.append(
                    f"score 必须是 0 到 1 之间的数字，实际为 {data.get('score')!r}"
                )
            feedback = "；".join(problems)
    raise ClassifyError(f"连续 {MAX_PARSE_ATTEMPTS} 次未得到合法输出，最后反馈：{feedback}")


def main():
    # 个别环境终端不是 UTF-8，显式指定避免中文输出炸掉
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(
            f"错误：未设置环境变量 {API_KEY_ENV}（智谱开放平台 API Key），"
            "请先 export 后再运行。",
            file=sys.stderr,
        )
        return 2

    failed = 0
    with requests.Session() as session:
        session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
        for text in TEXTS:
            try:
                result = classify(session, text)
            except ClassifyError as exc:
                failed += 1
                print(f"[失败] {text}：{exc}", file=sys.stderr)
                continue
            # stdout 上只有结果本身：每条一行、恰好两个字段，供下游按行入库
            print(json.dumps(result, ensure_ascii=False))

    if failed:
        print(
            f"{failed}/{len(TEXTS)} 条分类失败，失败条目不写入 stdout，避免脏数据入库。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
