#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 GLM 对一批中文文本做情感三分类，输出严格符合入库约束的 JSON。

下游数据库约束（字段名与取值都不能错）：
    {"sentiment": "正面" | "负面" | "中性", "score": 0 到 1 之间的数字}

关键设计（来自 bigmodel-cn 接入实测）：
1. 智谱平台没有 strict JSON Schema 强约束（response_format 只有 text / json_object
   两种取值，传 json_schema 会被静默忽略），所以 json_object 只能保证"输出是 JSON"，
   不能保证结构正确。必须：prompt 里写死目标结构 + 客户端严格校验 + 不合格重试。
2. 思考 token 计入 max_tokens 预算，预算小了会拿到 finish_reason=length 的空内容；
   本任务是简单分类，直接用 thinking: disabled 关闭思考，规避该问题。
3. 每条文本独立请求、独立校验、独立重试；校验失败会带着失败原因重试，重试耗尽则
   整体以非零码退出，stdout 只输出通过校验的记录——宁可不入库，也不写脏数据。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys
import time

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.2"  # thinking 可显式关闭（glm-5.3 在标准端点强制思考，简单分类没必要）
MAX_ATTEMPTS = 3
VALID_SENTIMENTS = ("正面", "负面", "中性")

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是一个中文评论情感分类器。对用户给出的文本做情感三分类并给出置信度。\n"
    "你必须只输出一个 JSON 对象，禁止输出任何解释、前后缀文字或代码块标记，"
    "结构严格如下：\n"
    '{"sentiment": "正面", "score": 0.95}\n'
    "字段约束：\n"
    '1. sentiment 只能取 "正面"、"负面"、"中性" 三个中文字符串之一；'
    "情感明显积极选正面，明显消极选负面，无所谓好坏或褒贬不明显选中性。\n"
    "2. score 是 0 到 1 之间（含边界）的数字，表示该分类的置信度。\n"
    "3. 只允许 sentiment 和 score 两个字段，不得新增、改名或缺失。"
)


class ApiCallError(Exception):
    """API 调用层面的可重试错误（网络、HTTP、API 错误码、空内容等）。"""


def _log(msg):
    print(msg, file=sys.stderr)


def _call_api(session, api_key, messages):
    """发起一次对话补全请求，返回 message.content 字符串。失败抛 ApiCallError。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        # 平台不支持 json_schema 强约束；json_object 只保证"是 JSON"，结构靠下面
        # 的 SYSTEM_PROMPT + 客户端 _validate 兜底。
        "response_format": {"type": "json_object"},
        # 简单分类任务不需要深度思考，显式关闭（思考 token 会挤占 max_tokens）。
        "thinking": {"type": "disabled"},
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    try:
        resp = session.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise ApiCallError(f"网络/请求异常：{exc}") from exc

    if resp.status_code != 200:
        raise ApiCallError(f"HTTP {resp.status_code}：{resp.text[:300]}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise ApiCallError(f"响应不是 JSON：{resp.text[:300]}") from exc

    if body.get("error"):
        err = body["error"]
        raise ApiCallError(
            f"API 错误 code={err.get('code')} message={err.get('message')}"
        )

    choices = body.get("choices") or []
    if not choices:
        raise ApiCallError(f"响应中没有 choices：{json.dumps(body, ensure_ascii=False)[:300]}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    # finish_reason != stop 说明内容被截断或异常终止（如 length：预算被耗尽），
    # 此时 content 不可信，按可重试错误处理。
    if finish_reason != "stop":
        raise ApiCallError(f"finish_reason={finish_reason!r}，内容可能不完整")

    content = (choice.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ApiCallError("content 为空字符串或不是字符串")
    return content


def _extract_json(content):
    """从模型输出中尽力解析出 JSON 对象，失败抛 ValueError。

    json_object 模式不保证输出"干净"：极端情况下仍可能夹带解释文字或 ``` 围栏，
    这里逐级兜底：原样解析 -> 剥围栏 -> 截取最外层花括号。
    """
    text = content.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass

    without_fences = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("```")
    ).strip()
    if without_fences:
        try:
            return json.loads(without_fences)
        except ValueError:
            pass
        start, end = without_fences.find("{"), without_fences.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(without_fences[start : end + 1])
            except ValueError:
                pass

    raise ValueError("无法从模型输出中解析出 JSON")


def _validate(data):
    """按入库约束做严格校验。返回 (归一化结果, None) 或 (None, 错误说明)。"""
    if not isinstance(data, dict):
        return None, "输出不是 JSON 对象"

    keys = set(data.keys())
    if keys != {"sentiment", "score"}:
        return None, f"字段集合不符，期望恰好为 {{sentiment, score}}，实际为 {sorted(keys)}"

    sentiment = data["sentiment"]
    if not isinstance(sentiment, str):
        return None, "sentiment 不是字符串"
    sentiment = sentiment.strip()
    if sentiment not in VALID_SENTIMENTS:
        return None, f"sentiment 取值非法 {sentiment!r}，只能是 正面/负面/中性"

    score = data["score"]
    if isinstance(score, bool):  # bool 是 int 的子类，要先排除
        return None, "score 是布尔值，不是数字"
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError:
            return None, f"score 不是数字：{score!r}"
    if not isinstance(score, (int, float)):
        return None, f"score 不是数字：{type(score).__name__}"
    score = float(score)
    if not 0.0 <= score <= 1.0:
        return None, f"score 超出 [0, 1] 区间：{score}"

    return {"sentiment": sentiment, "score": round(score, 4)}, None


def classify(session, api_key, text):
    """对单条文本做情感分类，带校验-纠错重试。全部失败抛 RuntimeError。"""
    base_user = f"待分类文本：{text}"
    last_error = "未知错误"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # 每轮都保持干净的 system+user 两轮结构，把上一轮的失败原因并进 user 消息
        # 让模型自我修正（不追加 assistant 轮，避免依赖多轮对话格式的行为差异）。
        user = (
            base_user
            if attempt == 1
            else f"{base_user}\n\n注意：你上一次的输出不合格（{last_error}）。"
            "请重新只输出一个严格符合要求的 JSON 对象，不要有任何多余内容。"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]

        try:
            content = _call_api(session, api_key, messages)
        except ApiCallError as exc:
            last_error = str(exc)
            _log(f"[尝试 {attempt}/{MAX_ATTEMPTS}] API 调用失败：{last_error}")
        else:
            try:
                data = _extract_json(content)
            except ValueError as exc:
                last_error = f"{exc}；原始输出：{content[:200]!r}"
                _log(f"[尝试 {attempt}/{MAX_ATTEMPTS}] 解析失败：{last_error}")
            else:
                result, error = _validate(data)
                if error is None:
                    return result
                last_error = f"{error}；解析结果：{json.dumps(data, ensure_ascii=False)[:200]}"
                _log(f"[尝试 {attempt}/{MAX_ATTEMPTS}] 校验失败：{last_error}")

        if attempt < MAX_ATTEMPTS:
            time.sleep(attempt)  # 简单退避：1s、2s

    raise RuntimeError(f"文本 {text!r} 重试 {MAX_ATTEMPTS} 次后仍不合规：{last_error}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        _log("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=你的Key")
        return 1

    session = requests.Session()
    failed = 0
    for text in TEXTS:
        try:
            result = classify(session, api_key, text)
        except RuntimeError as exc:
            _log(f"错误：{exc}")
            failed += 1
            continue
        # stdout 只输出通过校验的记录，每行一个严格 JSON，方便下游逐行入库
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
