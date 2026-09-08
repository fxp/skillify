"""用智谱 GLM 对文本做情感分类，输出严格符合 {"sentiment": ..., "score": ...} 的 JSON。

用法:
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

stdout 每行一个 JSON 对象（与输入文本顺序一致），字段固定为 sentiment / score，
可直接入库。平台没有 json_schema 严格模式（会被静默忽略），因此结构约束
靠 system prompt + 客户端校验兜底：解析失败或字段非法时重试，重试耗尽则
报错退出——宁可不写，也不写脏数据。
"""

import json
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = 60  # 秒

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

VALID_SENTIMENTS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是一个情感分类器，对用户给出的文本做三分类。"
    '只输出一个 JSON 对象，结构严格为 {"sentiment": "正面"|"负面"|"中性", "score": 0到1之间的小数}。'
    "规则：sentiment 只能取 正面、负面、中性 三者之一；score 是该分类的置信度，"
    "必须是 0 到 1 之间的小数；字段名必须完全是 sentiment 和 score，不能多字段、少字段或改名；"
    "不要输出 JSON 以外的任何文字、解释或代码块标记。"
)


def extract_json_object(text):
    """从模型输出中截出第一个完整的 JSON 对象。

    json_object 模式下模型仍可能夹带说明文字或 ```json 围栏，
    所以不做整串 loads，而是按花括号配对扫描（正确跳过字符串内的花括号）。
    """
    if not text:
        raise ValueError("模型 content 为空")
    start = text.find("{")
    if start == -1:
        raise ValueError("输出中不含 JSON 对象")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("JSON 对象不完整")


def validate_result(obj):
    """校验模型输出，返回只含 sentiment / score 两个键的新 dict。

    重建而不是透传原文，保证入库对象恰好是这两个字段。
    """
    if not isinstance(obj, dict):
        raise ValueError(f"输出不是 JSON 对象: {obj!r}")
    missing = {"sentiment", "score"} - set(obj)
    if missing:
        raise ValueError(f"缺少字段: {sorted(missing)}")

    sentiment = obj["sentiment"]
    if not isinstance(sentiment, str) or sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"sentiment 取值非法: {sentiment!r}")

    score = obj["score"]
    # bool 是 int 的子类，直接拒绝；数字字符串（如 "0.9"）容错转换
    if isinstance(score, bool):
        raise ValueError(f"score 不是数字: {score!r}")
    if not isinstance(score, (int, float)):
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise ValueError(f"score 不是数字: {score!r}")
    score = round(float(score), 4)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score 超出 [0,1]: {score}")

    return {"sentiment": sentiment, "score": score}


def classify_text(api_key, text):
    """对单条文本调 GLM 做情感分类，返回 {"sentiment": ..., "score": ...}。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"待分类文本：{text}"},
        ],
        "response_format": {"type": "json_object"},
        # glm-5.3 在标准端点强制开启思考（传 disabled 会报 1210），
        # 简单分类任务用最低推理档位即可；思考 token 计入 max_tokens，预算给足
        "thinking": {"type": "enabled"},
        "reasoning_effort": "low",
        "max_tokens": 2048,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # 网络抖动 / 解析失败 / 校验失败都可重试；4xx 配置类错误直接报错退出
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络错误: {exc}"
            print(f"  第 {attempt}/{MAX_ATTEMPTS} 次尝试失败：{last_err}", file=sys.stderr)
            continue

        if resp.status_code != 200:
            raise RuntimeError(f"API 返回 HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            body = resp.json()
            choice = body["choices"][0]
        except (ValueError, KeyError, IndexError) as exc:
            last_err = f"响应结构异常: {exc}; body={str(body)[:200]}"
            print(f"  第 {attempt}/{MAX_ATTEMPTS} 次尝试失败：{last_err}", file=sys.stderr)
            continue

        # 思考 token 可能吃光预算导致 content 为空，判据是 finish_reason 而不是空串
        finish_reason = choice.get("finish_reason")
        if finish_reason != "stop":
            last_err = (
                f"finish_reason={finish_reason!r}（max_tokens 预算不足或内容被拦截），"
                f"content={choice['message'].get('content')!r}"
            )
            print(f"  第 {attempt}/{MAX_ATTEMPTS} 次尝试失败：{last_err}", file=sys.stderr)
            continue

        try:
            raw = json.loads(extract_json_object(choice["message"].get("content")))
            return validate_result(raw)
        except (KeyError, ValueError) as exc:
            last_err = f"输出不符合约定结构: {exc}"
            print(f"  第 {attempt}/{MAX_ATTEMPTS} 次尝试失败：{last_err}", file=sys.stderr)
            continue

    raise RuntimeError(f"重试 {MAX_ATTEMPTS} 次仍无法得到合法结果：{last_err}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    results = []
    for idx, text in enumerate(TEXTS, 1):
        print(f"[{idx}/{len(TEXTS)}] 分类中: {text}", file=sys.stderr)
        results.append(classify_text(api_key, text))

    # stdout 只输出结果（每行一个严格符合结构的 JSON），进度信息走 stderr
    for result in results:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
