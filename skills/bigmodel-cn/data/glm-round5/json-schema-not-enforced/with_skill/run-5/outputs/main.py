"""用智谱 GLM 对文本做情感分类，输出严格符合 {"sentiment": "正面"|"负面"|"中性", "score": 0~1} 的 JSON。

注意：智谱 chat/completions 的 response_format 只支持 text / json_object，
json_schema 会被静默忽略，因此结构约束只能靠 system prompt 描述 + 客户端校验兜底。
"""

import json
import os
import sys
import time
import uuid

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-5.3"  # 标准端点强制思考，分类属轻量任务，下方用 reasoning_effort=low 降开销
VALID_SENTIMENTS = ("正面", "负面", "中性")
MAX_ATTEMPTS = 3  # 解析/校验失败时，带上纠错提示重试
BACKOFF_SECONDS = 1.0  # 429/5xx 的指数退避基数

TEXTS = [
    "这家店服务太差了，再也不来了",
    "东西还行吧，没什么特别的",
    "太惊喜了，比我预期好太多，强烈推荐",
]

SYSTEM_PROMPT = (
    "你是情感分类引擎。对用户给出的文本做情感分类，只输出一个 JSON 对象，"
    "不要输出任何解释、markdown 代码块或其他文字。结构严格为：\n"
    '{"sentiment": "正面" | "负面" | "中性", "score": 0.95}\n'
    "字段要求：\n"
    '1. sentiment 只能是 "正面"、"负面"、"中性" 三个字符串之一，禁止 positive/negative/neutral 或其他写法；\n'
    "2. score 是该分类的置信度，必须是 0 到 1 之间的数字，不能是字符串；\n"
    "3. 只包含这两个字段，禁止新增字段。"
)


class RetryableError(Exception):
    """可重试的错误：429/5xx、网络异常、finish_reason=network_error。"""


def _extract_content(data: dict) -> str:
    choice = data["choices"][0]
    finish_reason = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content")
    if finish_reason == "network_error" or not content or not content.strip():
        raise RetryableError(f"finish_reason={finish_reason!r}, content={content!r}")
    if finish_reason != "stop":
        # sensitive / length 等重试无意义，直接失败，避免产出脏数据
        raise RuntimeError(f"异常结束 finish_reason={finish_reason!r}")
    return content.strip()


def _call_api(api_key: str, messages: list) -> str:
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},  # 平台无 json_schema 强约束
            "do_sample": False,  # 贪心解码，分类结果稳定可复现
            "reasoning_effort": "low",  # glm-5.3 仅接受 low/high/max；low 近似不思考
            "max_tokens": 1024,
            "request_id": str(uuid.uuid4()),
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            detail = f"code={err.get('code')} message={err.get('message')}"
        except ValueError:
            detail = resp.text[:200]
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableError(f"HTTP {resp.status_code} {detail}")
        # 401/403/400 属配置或参数问题，重试无意义
        raise RuntimeError(f"HTTP {resp.status_code} {detail}")
    return _extract_content(resp.json())


def _parse_and_validate(raw: str) -> dict:
    # json_object 模式下模型仍可能夹带文字，取首尾大括号之间的部分再解析
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"返回中找不到 JSON 对象: {raw!r}")
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: {exc}; 原文: {raw!r}") from exc

    sentiment = obj.get("sentiment")
    if isinstance(sentiment, str):
        sentiment = sentiment.strip()
    if sentiment not in VALID_SENTIMENTS:
        raise ValueError(
            f"sentiment 取值非法: {sentiment!r}，只能是 {'/'.join(VALID_SENTIMENTS)}"
        )

    score = obj.get("score")
    if isinstance(score, bool):
        raise ValueError("score 不能是布尔值")
    try:
        score = float(score)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"score 必须是数字: {score!r}") from exc
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"score 必须在 0 到 1 之间: {score}")

    # 显式重建 dict，保证字段名精确、无多余字段，入库前结构可控
    return {"sentiment": sentiment, "score": round(score, 4)}


def classify_text(api_key: str, text: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = _call_api(api_key, messages)
        except RetryableError as exc:
            last_error = exc
            time.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
            continue  # 传输层问题，原样重发
        try:
            return _parse_and_validate(raw)
        except ValueError as exc:
            last_error = exc
            # do_sample=False 下重发同样请求会得到同样输出，必须追加纠错上下文
            messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"你上次的输出不符合要求：{exc}。请重新输出，"
                        '且只输出一个 JSON 对象：{"sentiment": "正面"|"负面"|"中性", '
                        '"score": 0到1之间的数字}，不要有任何其他文字。'
                    ),
                },
            ]
    raise RuntimeError(f"重试 {MAX_ATTEMPTS} 次后仍失败: {last_error}")


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    failed = False
    for text in TEXTS:
        try:
            result = classify_text(api_key, text)
        except Exception as exc:  # 单条失败不产出任何结果行，避免脏数据入库
            print(f"文本 {text!r} 分类失败: {exc}", file=sys.stderr)
            failed = True
            continue
        # stdout 每行一个严格符合结构的 JSON 对象，可直接逐行入库
        print(json.dumps(result, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
