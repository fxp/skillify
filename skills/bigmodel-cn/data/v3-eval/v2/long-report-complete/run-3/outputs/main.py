#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 生成《2026 年中国新能源汽车出口》市场简报。

- 模型: glm-5.3, 同步对话补全 POST /paas/v4/chat/completions (open.bigmodel.cn)
- 依赖: 仅 requests; API Key 从环境变量 ZHIPUAI_API_KEY 读取
- 简报要求: 不少于 600 字(按非空白字符计), 带小标题和具体数据

完整性保障(拿到残缺内容时在脚本内部消化, 绝不把半截内容交给调用方):
1. 显式给足 max_tokens —— glm-5.3 在标准端点强制开启深度思考, 且思考 token
   计入 max_tokens, 预算不足时会出现 finish_reason=length 甚至空内容;
2. 只把 finish_reason == "stop" 的产出视为完整; 若因 length 截断, 自动带着
   已生成内容发起续写并拼接(含重叠去重), 最多续写 6 轮;
3. 成文后做结构校验(字数 / 小标题 / 具体数据 / 结尾标点), 不合格则换更大的
   token 预算整篇重新生成, 最多 3 次;
4. 全部通过后才打印全文, 并输出字数与完整性的明确确认; 彻底失败则以非零
   码退出, 不输出任何半成品。
"""

import os
import re
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"

MIN_CHARS = 600             # 硬性字数下限(非空白字符)
MIN_HEADINGS = 2            # 至少 2 个小标题
MIN_DATA_POINTS = 5         # 至少 5 处具体数字
MAX_CONTINUATION_ROUNDS = 6 # 单次生成内的最大续写轮数
HTTP_RETRIES = 3            # 网络错误 / 429 / 5xx 的退避重试次数
REQUEST_TIMEOUT = 180
# 逐次升级的输出预算(接口上限 131072; 思考 token 也计入, 故从宽给)
TOKEN_BUDGETS = (16384, 65536, 131072)

SYSTEM_PROMPT = (
    "你是一名资深汽车行业市场分析师, 负责为管理层周报撰写市场简报。"
    "写作风格: 结论先行、数据翔实、语言精炼, 只用简体中文。"
)

USER_PROMPT = """请撰写一篇题为《2026年中国新能源汽车出口市场简报》的报告, 要求:
1. 正文不少于 700 字;
2. 使用 Markdown 二级小标题(## 开头)划分至少 4 个板块, 依次覆盖: 整体出口规模与增速、主要出口目的地市场、头部车企与车型表现、挑战风险与趋势展望;
3. 每个板块都必须引用具体数据(出口量、同比增速、出口金额、市场份额、单车均价等, 基于行业公开信息给出合理估计);
4. 最后以"## 总结"收束全文, 总结段落以完整句子和句号结束;
5. 直接输出简报正文本身, 不要输出任何解释、前言、代码块围栏或多余标记。"""

CONTINUE_PROMPT = (
    "继续写。请从你刚才中断的位置接着写, 不要重复已写内容, "
    "不要任何开场白, 直接续写正文, 补完全部剩余板块直到全文自然收尾。"
)


class GlmApiError(Exception):
    """API 调用失败。retryable=True 表示重试或换预算可能有救。"""

    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


class ReportValidationError(Exception):
    """产出内容未通过完整性/结构校验(可换预算整篇重试)。"""


# ---------------------------------------------------------------- API 调用

def _format_api_error(body):
    err = (body or {}).get("error") or {}
    return "code=%s, message=%s" % (err.get("code"), err.get("message"))


def call_glm(api_key, messages, max_tokens):
    """发起一次同步对话补全, 返回 (content, finish_reason)。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.6,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    last_error = "未知错误"
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = "网络错误: %s" % exc
        else:
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError:
                    last_error = "响应不是合法 JSON"
                else:
                    if isinstance(body, dict) and body.get("error"):
                        last_error = _format_api_error(body)
                    else:
                        choice = (body.get("choices") or [{}])[0]
                        content = ((choice.get("message") or {}).get("content")) or ""
                        return content, choice.get("finish_reason")
            else:
                try:
                    detail = _format_api_error(resp.json())
                except ValueError:
                    detail = (resp.text or "")[:300]
                # 4xx 属于鉴权/参数类问题, 重试无意义; 429/5xx 退避后重试
                if resp.status_code != 429 and resp.status_code < 500:
                    raise GlmApiError(
                        "API 请求失败(HTTP %s): %s" % (resp.status_code, detail),
                        retryable=False,
                    )
                last_error = "HTTP %s: %s" % (resp.status_code, detail)
        if attempt < HTTP_RETRIES:
            time.sleep(2 ** attempt)
    raise GlmApiError("API 请求连续 %d 次失败, 最后错误: %s"
                      % (HTTP_RETRIES, last_error))


# ---------------------------------------------------------------- 文本工具

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*[^\s#]"
    r"|[一二三四五六七八九十百]{1,3}[、.．:：]"
    r"|\d{1,2}[、.．]\s*[^\s])"
)
_TERMINAL_CHARS = '。！？…”』」》）)]'


def clean_text(text):
    """去掉思考标签、代码块围栏等多余包装。"""
    text = _THINK_RE.sub("", text).strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def count_chars(text):
    """字数 = 非空白字符数(中文简报的通行口径)。"""
    return len(re.sub(r"\s+", "", text))


def count_headings(text):
    return sum(1 for line in text.splitlines() if _HEADING_RE.match(line))


def count_data_points(text):
    return len(re.findall(r"\d+(?:\.\d+)?", text))


def ends_completely(text):
    return bool(text.rstrip()) and text.rstrip()[-1] in _TERMINAL_CHARS


def merge_continuation(previous, continuation):
    """拼接续写内容; 模型常会复述中断点附近的文字, 先做最长重叠去重。"""
    continuation = continuation.lstrip()
    window = min(len(previous), len(continuation), 120)
    # 下限取 1: 中断点经常落在数字/单词内部(如 "8" + "50万辆"), 单字符对齐也能拼对
    for size in range(window, 0, -1):
        if previous.endswith(continuation[:size]):
            return previous + continuation[size:]
    return previous + continuation


def validate_report(text):
    """返回问题列表; 空列表表示合格。"""
    problems = []
    chars = count_chars(text)
    if chars < MIN_CHARS:
        problems.append("字数不足(%d < %d)" % (chars, MIN_CHARS))
    headings = count_headings(text)
    if headings < MIN_HEADINGS:
        problems.append("小标题不足(%d < %d)" % (headings, MIN_HEADINGS))
    data_points = count_data_points(text)
    if data_points < MIN_DATA_POINTS:
        problems.append("具体数据不足(%d 处 < %d 处)" % (data_points, MIN_DATA_POINTS))
    if not ends_completely(text):
        problems.append("结尾不完整(未以终止标点收尾, 疑似截断)")
    return problems


# ---------------------------------------------------------------- 生成流程

def generate_once(api_key, max_tokens):
    """完整走一次「生成 -> (必要时)续写拼接 -> 校验」流程, 失败抛异常。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]
    content, finish_reason = call_glm(api_key, messages, max_tokens)
    if not content:
        # 典型成因: 思考 token 吃光了 max_tokens 预算, 换更大预算重试才有意义
        raise ReportValidationError(
            "首轮返回空内容(finish_reason=%s), 疑似 max_tokens 预算被思考消耗"
            % finish_reason)

    full = clean_text(content)
    rounds = 0
    while finish_reason == "length":
        if rounds >= MAX_CONTINUATION_ROUNDS:
            raise ReportValidationError("已续写 %d 轮仍因 max_tokens 截断, 放弃本篇"
                                        % rounds)
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": CONTINUE_PROMPT})
        content, finish_reason = call_glm(api_key, messages, max_tokens)
        if not content:
            raise ReportValidationError("续写返回空内容(finish_reason=%s)"
                                        % finish_reason)
        full = merge_continuation(full, clean_text(content))
        rounds += 1

    if finish_reason != "stop":
        # sensitive / network_error / model_context_window_exceeded 等, 产出不可信
        raise ReportValidationError("生成异常终止: finish_reason=%s" % finish_reason)

    problems = validate_report(full)
    if problems:
        raise ReportValidationError("结构校验未通过: " + "; ".join(problems))
    return full, finish_reason, rounds


def deliver(report, finish_reason, continuation_rounds, budget):
    """打印全文与交付确认。只有校验通过的内容才会走到这里。"""
    chars = count_chars(report)
    headings = count_headings(report)
    data_points = count_data_points(report)
    print("=" * 18 + " 2026年中国新能源汽车出口市场简报(全文) " + "=" * 18)
    print()
    print(report)
    print()
    print("=" * 28 + " 交付确认 " + "=" * 28)
    print("字数统计: %d 字(按非空白字符计, 要求 >= %d 字)" % (chars, MIN_CHARS))
    print("结构检查: 检出 %d 个小标题(要求 >= %d 个)" % (headings, MIN_HEADINGS))
    print("数据检查: 检出 %d 处具体数字(要求 >= %d 处)" % (data_points, MIN_DATA_POINTS))
    print("完整性检查: finish_reason=%s(自然收尾), 截断续写 %d 轮, max_tokens=%d"
          % (finish_reason, continuation_rounds, budget))
    print("[OK] 字数达标: %d 字 >= %d 字" % (chars, MIN_CHARS))
    print("[OK] 内容完整: 小标题、具体数据、完整结尾均通过校验, 以上为全文, 无截断")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 未检测到环境变量 ZHIPUAI_API_KEY。\n"
              "请先在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取 API Key,\n"
              "然后执行: export ZHIPUAI_API_KEY=<你的Key>", file=sys.stderr)
        return 1

    for attempt, budget in enumerate(TOKEN_BUDGETS, start=1):
        try:
            report, finish_reason, rounds = generate_once(api_key, budget)
        except GlmApiError as exc:
            print("[第 %d 次尝试] API 调用失败: %s" % (attempt, exc), file=sys.stderr)
            if not exc.retryable:
                break
        except ReportValidationError as exc:
            print("[第 %d 次尝试] %s" % (attempt, exc), file=sys.stderr)
        else:
            deliver(report, finish_reason, rounds, budget)
            return 0

    print("生成失败: 多次尝试后仍未得到完整达标的简报。\n"
          "为避免交付残缺内容, 本次不输出任何半成品; 请检查网络、Key 与账户额度后重试。",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
