#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱开放平台（BigModel）的
Chat Completions 接口把每条反馈抽取成结构化信息，写出同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
    name        反馈人姓名
    issue_type  问题类型（模型自行归类）
    urgency     紧急程度，只能是 low / medium / high 之一

环境变量：
    ZHIPUAI_API_KEY   必填，智谱开放平台 API Key
    ZHIPUAI_MODEL     选填，默认 glm-4.6
    ZHIPUAI_BASE_URL  选填，默认 https://open.bigmodel.cn/api/paas/v4

只依赖标准库 + requests。
"""

import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(HERE, "feedback.txt")
OUTPUT_FILE = os.path.join(HERE, "out.json")

BASE_URL = os.environ.get("ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
CHAT_URL = BASE_URL + "/chat/completions"
MODEL = os.environ.get("ZHIPUAI_MODEL", "glm-4.6")

ALLOWED_URGENCY = ("low", "medium", "high")
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3

SYSTEM_PROMPT = """你是一个客户反馈信息抽取器。用户会给你一条客户反馈原文。
请抽取以下三个字段，并且只输出一个 JSON 对象（不要输出解释、不要输出 Markdown 代码块）：

{
  "name": "反馈人姓名；如果原文没有明确姓名，填 \\"未知\\"",
  "issue_type": "问题类型，用简短的中文名词短语概括，例如 \\"物流延迟\\"、\\"退款问题\\"、\\"产品质量\\"、\\"账号登录\\"、\\"客服态度\\"、\\"计费错误\\"、\\"功能建议\\" 等，可自行归类",
  "urgency": "紧急程度，只能是 low、medium、high 三者之一"
}

urgency 判断参考：
- high：业务中断、资金损失、数据丢失、安全问题、明确表示要投诉/退款/上门，或强烈情绪与时间压力。
- medium：功能受影响但仍可使用、需要尽快处理但无立即损失。
- low：一般咨询、建议、轻微不便、表扬。

严格只输出 JSON 对象，键名必须是 name、issue_type、urgency。"""


def read_feedback(path):
    if not os.path.exists(path):
        sys.exit("找不到输入文件：%s" % path)
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line]


def extract_json_object(text):
    """从模型返回的文本里尽量解析出一个 JSON 对象。"""
    if not text:
        return None
    text = text.strip()

    # 去掉可能的 ```json ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass

    # 退而求其次：截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
    return None


def call_model(api_key, feedback):
    """调用一次对话补全接口，返回模型输出的纯文本。"""
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "客户反馈原文：\n" + feedback},
        ],
        "temperature": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                CHAT_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise ValueError("响应中没有 choices：%s" % json.dumps(data, ensure_ascii=False)[:300])
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                if isinstance(content, list):  # 兼容分块内容格式
                    content = "".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                return content
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = "HTTP %s: %s" % (resp.status_code, resp.text[:300])
            else:
                raise RuntimeError("HTTP %s: %s" % (resp.status_code, resp.text[:500]))
        except requests.RequestException as exc:
            last_err = str(exc)

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)

    raise RuntimeError("请求失败（已重试 %d 次）：%s" % (MAX_RETRIES, last_err))


def normalize(record, feedback):
    """把模型返回的对象规整成恰好三个键，并校验 urgency 取值。"""
    record = record if isinstance(record, dict) else {}

    name = record.get("name")
    name = str(name).strip() if name not in (None, "") else "未知"

    issue_type = record.get("issue_type")
    issue_type = str(issue_type).strip() if issue_type not in (None, "") else "其他"

    urgency = str(record.get("urgency", "")).strip().lower()
    if urgency not in ALLOWED_URGENCY:
        # 常见别名兜底
        alias = {
            "低": "low", "中": "medium", "高": "high",
            "normal": "medium", "moderate": "medium",
            "urgent": "high", "critical": "high", "严重": "high",
        }
        urgency = alias.get(urgency, "medium")
        print("  ! urgency 取值异常，已回退为 %s（原文：%s）" % (urgency, feedback[:30]),
              file=sys.stderr)

    return {"name": name, "issue_type": issue_type, "urgency": urgency}


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    feedbacks = read_feedback(INPUT_FILE)
    if not feedbacks:
        sys.exit("feedback.txt 为空，没有可处理的反馈")

    print("共 %d 条反馈，使用模型 %s" % (len(feedbacks), MODEL))

    results = []
    for idx, feedback in enumerate(feedbacks, 1):
        print("[%d/%d] %s" % (idx, len(feedbacks), feedback[:40]))
        try:
            content = call_model(api_key, feedback)
            parsed = extract_json_object(content)
            if parsed is None:
                print("  ! 无法解析模型输出，使用兜底值。原始输出：%s" % (content or "")[:200],
                      file=sys.stderr)
            results.append(normalize(parsed, feedback))
        except Exception as exc:  # 单条失败不影响整体产出
            print("  ! 第 %d 条处理失败：%s" % (idx, exc), file=sys.stderr)
            results.append({"name": "未知", "issue_type": "处理失败", "urgency": "medium"})

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("已写出 %s（%d 条）" % (OUTPUT_FILE, len(results)))


if __name__ == "__main__":
    main()
