#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱开放平台（bigmodel.cn）
的 GLM 模型把每条反馈抽取成结构化信息，结果写入同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
    name        反馈人姓名
    issue_type  问题类型（由模型自行归类）
    urgency     紧急程度，取值只能是 low / medium / high

依赖：仅 requests（标准库之外）。
运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import random
import re
import sys
import time

import requests

# ---------------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------------

# 智谱开放平台标准 API（注意：GLM Coding Plan 套餐 Key 不能打这个端点，
# 否则会返回 HTTP 429 + 错误码 1113「余额不足」，那种情况要改用
# https://open.bigmodel.cn/api/coding/paas/v4/chat/completions）
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

# glm-4.6：200K 上下文，工具调用/推理能力强，且 thinking 可显式关闭（抽取任务不需要思考，
# 关掉更快更省 token）。可用环境变量 GLM_MODEL 覆盖，例如免费的 glm-4.5-flash。
MODEL = os.environ.get("GLM_MODEL", "glm-4.6")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "feedback.txt")
OUTPUT_PATH = os.path.join(BASE_DIR, "out.json")

ALLOWED_URGENCY = ("low", "medium", "high")

REQUEST_TIMEOUT = 120       # 单次请求超时（秒）
MAX_RETRIES = 4             # 网络/限流错误的最大重试次数
MAX_PARSE_RETRIES = 2       # 模型返回不合法 JSON 时的额外重试次数

SYSTEM_PROMPT = """你是一个客户反馈信息抽取助手。用户会给你一条客户反馈原文，\
你需要从中抽取结构化信息，并且只返回一个 JSON 对象，不要输出任何解释、前后缀或 Markdown 代码块。

JSON 对象必须恰好包含以下三个键，不能多也不能少：
{
  "name": "反馈人姓名（字符串）。从原文中提取；如果原文没有提到姓名，填 \\"未知\\"。",
  "issue_type": "问题类型（字符串，中文简短名词短语，由你自己归类，例如 \\"物流延迟\\"、\\"产品质量\\"、\\"退款问题\\"、\\"客服态度\\"、\\"功能建议\\"、\\"账单错误\\" 等）。同类问题请使用一致的措辞。",
  "urgency": "紧急程度（字符串），取值只能是 \\"low\\"、\\"medium\\"、\\"high\\" 三者之一，小写。"
}

紧急程度判断标准：
- high：业务已中断、资金损失、安全风险、客户明确表达强烈不满或威胁投诉/退款/流失。
- medium：功能受影响但仍可使用，客户有明显不满但语气尚可，需要尽快处理。
- low：一般咨询、建议、轻微不便，或客户情绪平和。

再次强调：只输出那一个 JSON 对象本身。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def read_feedback(path):
    """按行读取反馈，去掉空行与首尾空白。"""
    if not os.path.exists(path):
        sys.exit("找不到输入文件：{}".format(path))
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line]


def extract_json_object(text):
    """
    尽最大努力把模型返回的文本解析成 dict。

    智谱平台没有 response_format.type = "json_schema" 这种强约束模式
    （传了会被静默忽略），json_object 模式下模型偶尔仍可能夹带代码块或说明文字，
    所以这里做一层兜底解析。
    """
    if not text:
        return None
    text = text.strip()

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        pass

    # 去掉 ```json ... ``` 之类的围栏
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fenced:
        try:
            obj = json.loads(fenced.group(1))
            return obj if isinstance(obj, dict) else None
        except ValueError:
            pass

    # 最后退而求其次：截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except ValueError:
            pass

    return None


def normalize_record(obj, fallback_text):
    """把模型返回的对象规整成恰好三个键的记录；不合法时返回 None。"""
    if not isinstance(obj, dict):
        return None

    name = obj.get("name")
    issue_type = obj.get("issue_type")
    urgency = obj.get("urgency")

    name = str(name).strip() if name is not None else ""
    issue_type = str(issue_type).strip() if issue_type is not None else ""
    urgency = str(urgency).strip().lower() if urgency is not None else ""

    if urgency not in ALLOWED_URGENCY:
        # 常见偏差：中文、大写、带修饰词
        mapping = {
            "高": "high", "紧急": "high", "非常紧急": "high", "urgent": "high",
            "中": "medium", "中等": "medium", "一般": "medium", "normal": "medium",
            "低": "low", "不紧急": "low",
        }
        urgency = mapping.get(urgency, "")

    if not name:
        name = "未知"
    if not issue_type or not urgency:
        return None

    del fallback_text  # 仅用于调用方语义，规整阶段不需要
    return {"name": name, "issue_type": issue_type, "urgency": urgency}


def call_model(api_key, feedback, session):
    """
    调用一次 chat/completions，返回 message.content 字符串。
    对 429 / 5xx 做指数退避重试；4xx 配置类错误直接抛出（重试没有意义）。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "客户反馈原文：\n{}".format(feedback)},
        ],
        # 平台只支持 text / json_object 两种取值（没有 json_schema）
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 512,
    }
    # glm-4.6 及 glm-5.x 支持显式关闭深度思考；glm-4.5 以下不认这个参数，
    # glm-5.3 在标准端点关不掉（会报 1210），所以只对确定支持的模型传。
    if MODEL.startswith(("glm-4.6", "glm-5.2", "glm-5.1", "glm-5-", "glm-5v")):
        payload["thinking"] = {"type": "disabled"}

    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.post(
                API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = "网络错误：{}".format(exc)
        else:
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError("响应中没有 choices：{}".format(data))
                return choices[0].get("message", {}).get("content", "")

            body = resp.text[:500]
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = "HTTP {}：{}".format(resp.status_code, body)
            else:
                # 401/403/400 等是 Key 或参数问题，重试无意义
                raise RuntimeError(
                    "请求失败 HTTP {}：{}".format(resp.status_code, body)
                )

        if attempt < MAX_RETRIES - 1:
            delay = (2 ** attempt) + random.random()
            print("  [重试 {}/{}] {}，{:.1f}s 后重试".format(
                attempt + 1, MAX_RETRIES - 1, last_error, delay), file=sys.stderr)
            time.sleep(delay)

    raise RuntimeError("多次重试后仍然失败：{}".format(last_error))


def extract_one(api_key, feedback, session):
    """抽取单条反馈；JSON 不合法或字段缺失时重试若干次，仍失败则返回 None。"""
    for _ in range(1 + MAX_PARSE_RETRIES):
        content = call_model(api_key, feedback, session)
        record = normalize_record(extract_json_object(content), feedback)
        if record is not None:
            return record
        print("  模型返回不是合法的目标 JSON，重试一次：{!r}".format(
            (content or "")[:200]), file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit(
            "未设置环境变量 ZHIPUAI_API_KEY。\n"
            "请到 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取 API Key，然后：\n"
            "  export ZHIPUAI_API_KEY=your_key"
        )

    feedbacks = read_feedback(INPUT_PATH)
    if not feedbacks:
        print("feedback.txt 为空，写出空数组。")
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
            f.write("\n")
        return

    print("共读取 {} 条反馈，使用模型 {}".format(len(feedbacks), MODEL))

    results = []
    failed = 0
    session = requests.Session()
    for idx, feedback in enumerate(feedbacks, 1):
        preview = feedback if len(feedback) <= 40 else feedback[:40] + "…"
        print("[{}/{}] {}".format(idx, len(feedbacks), preview))
        try:
            record = extract_one(api_key, feedback, session)
        except RuntimeError as exc:
            print("  抽取失败：{}".format(exc), file=sys.stderr)
            record = None

        if record is None:
            failed += 1
            # 保底占位，保证输出条数与输入一一对应且键结构合法
            record = {"name": "未知", "issue_type": "未识别", "urgency": "medium"}
        results.append(record)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("已写出 {} 条结果到 {}".format(len(results), OUTPUT_PATH))
    if failed:
        print("其中 {} 条抽取失败，已用占位记录填充。".format(failed), file=sys.stderr)


if __name__ == "__main__":
    main()
