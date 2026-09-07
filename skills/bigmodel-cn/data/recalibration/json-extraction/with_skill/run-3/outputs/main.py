#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱开放平台（bigmodel.cn）
的 GLM 模型把每条反馈抽取成结构化信息，写出同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
    name        —— 反馈人姓名
    issue_type  —— 问题类型（模型自行归类）
    urgency     —— 紧急程度，只能是 "low" / "medium" / "high"

用法：
    export ZHIPUAI_API_KEY=你的标准 API Key      # 控制台：https://bigmodel.cn/usercenter/proj-mgmt/apikeys
    python3 main.py

依赖：仅 requests（其余均为标准库）。
"""

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 智谱开放平台标准 API（注意：GLM Coding Plan 编程套餐 Key 不能打这个端点，
# 会返回 HTTP 429 + 业务错误码 1113；套餐 Key 需改用 .../api/coding/paas/v4）。
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# 模型代码见 references/models.md。glm-5.3 在标准端点强制开启思考，无法通过
# thinking:{"type":"disabled"} 关闭（会报 1210），只能用 reasoning_effort 调档，
# 这里抽取任务不需要深度推理，用 low（实测 reasoning_tokens≈0，最省时省钱）。
MODEL = "glm-5.3"
REASONING_EFFORT = "low"  # glm-5.3 仅接受 max / high / low

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "feedback.txt")
OUTPUT_PATH = os.path.join(BASE_DIR, "out.json")

ALLOWED_URGENCY = ("low", "medium", "high")
REQUIRED_KEYS = ("name", "issue_type", "urgency")

MAX_WORKERS = 4        # 智谱按并发数限流，不要无限制并发
MAX_ATTEMPTS = 4       # 单条反馈的最大尝试次数（含首次）
REQUEST_TIMEOUT = 120  # 秒

SYSTEM_PROMPT = (
    "你是客户反馈信息抽取助手。用户会给你一条客户反馈，请抽取结构化信息并"
    "只返回一个 JSON 对象，不要输出任何解释文字、不要用 Markdown 代码块包裹。\n"
    "JSON 必须恰好包含以下三个键：\n"
    '  "name": 字符串，反馈人的姓名；如果反馈里没有出现姓名，填 "未知"。\n'
    '  "issue_type": 字符串，你对这条反馈的问题类型归类，用简短的中文名词短语'
    "（如 \"物流延迟\"、\"退款问题\"、\"产品质量\"、\"账号登录\"、\"客服态度\"、\"功能建议\"）。\n"
    '  "urgency": 字符串，紧急程度，只能是 "low"、"medium"、"high" 三者之一（小写英文）。\n'
    "判断 urgency 的参考：影响资金安全、账号无法使用、服务完全中断、"
    "客户明确表达强烈不满或要投诉/退货 → high；功能受损但仍可使用、"
    "客户表达明显不满 → medium；一般咨询、建议、轻微体验问题 → low。\n"
    '示例输出：{"name": "张三", "issue_type": "物流延迟", "urgency": "medium"}'
)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def read_feedback_lines(path):
    """按行读取反馈，去掉空行；返回 [(行号, 文本), ...]。"""
    if not os.path.exists(path):
        sys.exit("找不到输入文件：%s" % path)
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            text = raw.strip()
            if text:
                lines.append((lineno, text))
    if not lines:
        sys.exit("输入文件 %s 里没有有效的反馈内容。" % path)
    return lines


def strip_code_fence(text):
    """模型偶尔会用 ```json ... ``` 包裹，兜底剥掉。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def extract_json_object(text):
    """从模型输出里解析出 JSON 对象；解析失败时再尝试截取首个 {...} 片段。"""
    text = strip_code_fence(text)
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def normalize_record(obj, fallback_text):
    """校验并规整成恰好三个键的记录；不合法时抛 ValueError 触发重试。"""
    if not isinstance(obj, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    for key in REQUIRED_KEYS:
        if key not in obj:
            raise ValueError("模型返回缺少字段 %s" % key)

    name = str(obj["name"]).strip() or "未知"
    issue_type = str(obj["issue_type"]).strip() or "其他"
    urgency = str(obj["urgency"]).strip().lower()
    if urgency not in ALLOWED_URGENCY:
        raise ValueError("urgency 取值非法：%r" % obj["urgency"])

    del fallback_text  # 仅用于调用方定位问题
    # 显式重建，保证恰好三个键、且键顺序固定
    return {"name": name, "issue_type": issue_type, "urgency": urgency}


class ApiError(Exception):
    """调用失败；retryable 标记该错误是否值得退避重试。"""

    def __init__(self, message, retryable):
        Exception.__init__(self, message)
        self.retryable = retryable


def call_model(session, api_key, feedback):
    """调用一次 chat/completions，返回 message.content 字符串。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": feedback},
        ],
        # 平台不支持 json_schema 强约束（传了会被静默忽略），
        # 只能用 json_object + prompt 里写清字段结构，并在客户端做校验兜底。
        "response_format": {"type": "json_object"},
        "reasoning_effort": REASONING_EFFORT,
        "temperature": 0.1,
        "max_tokens": 512,
    }
    resp = session.post(
        API_URL,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code != 200:
        # 业务错误码在响应体 error.code 里，比 HTTP 状态码更具体。
        try:
            err = resp.json().get("error", {})
            detail = "%s %s" % (err.get("code", ""), err.get("message", ""))
        except ValueError:
            detail = resp.text[:200]
        # 401/403/400 是配置或参数问题，重试没有意义；429/5xx 才值得退避重试。
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise ApiError("HTTP %s: %s" % (resp.status_code, detail.strip()), retryable)

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ApiError("响应结构异常：%s" % json.dumps(data, ensure_ascii=False)[:200], False)


def process_one(session, api_key, index, lineno, feedback):
    """带重试地处理一条反馈，始终返回一条合法记录（彻底失败时降级填充）。"""
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            content = call_model(session, api_key, feedback)
            record = normalize_record(extract_json_object(content), feedback)
            return index, record
        except ApiError as exc:
            last_err = exc
            if not exc.retryable:
                break
        except (ValueError, TypeError, requests.RequestException) as exc:
            # JSON 解析/字段校验失败或网络抖动，都可以再试一次
            last_err = exc

        if attempt < MAX_ATTEMPTS:
            # 指数退避 + 抖动，避免固定间隔高频重试加重限流
            time.sleep(min(2 ** (attempt - 1), 8) + random.random())

    sys.stderr.write(
        "[警告] 第 %d 行反馈抽取失败（%s），已降级填充。\n" % (lineno, last_err)
    )
    return index, {"name": "未知", "issue_type": "抽取失败", "urgency": "medium"}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台标准 API Key）：\n"
            "    export ZHIPUAI_API_KEY=你的Key\n"
            "Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys"
        )

    entries = read_feedback_lines(INPUT_PATH)
    print("共读取 %d 条反馈，开始调用 %s 抽取……" % (len(entries), MODEL))

    results = [None] * len(entries)
    session = requests.Session()
    try:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(entries))) as pool:
            futures = [
                pool.submit(process_one, session, api_key, i, lineno, text)
                for i, (lineno, text) in enumerate(entries)
            ]
            done = 0
            for fut in futures:
                index, record = fut.result()
                results[index] = record
                done += 1
                print("  [%d/%d] %s / %s / %s" % (
                    done, len(entries),
                    record["name"], record["issue_type"], record["urgency"],
                ))
    finally:
        session.close()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("已写出 %s（%d 条记录）。" % (OUTPUT_PATH, len(results)))


if __name__ == "__main__":
    main()
