#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取同目录下的 feedback.txt（每行一条客户反馈），调用智谱开放平台（bigmodel.cn）
的 GLM 模型把每条反馈抽取成结构化信息，最后写出同目录下的 out.json。

out.json 是一个 JSON 数组，每个元素恰好包含三个键：
    name        反馈人姓名
    issue_type  问题类型（模型自行归类）
    urgency     紧急程度，只能是 low / medium / high

用法：
    export ZHIPUAI_API_KEY="你的标准 API Key"     # 从 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取
    python3 main.py

依赖：仅 requests。
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 智谱标准 API（注意：GLM Coding Plan 编程套餐的 Key 不能打这个端点，
# 套餐 Key 要用 https://open.bigmodel.cn/api/coding/paas/v4/chat/completions，
# 否则会报 HTTP 429 + 错误码 1113「余额不足」，那并不是真的需要充值）。
BASE_URL = os.environ.get(
    "ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
).rstrip("/")
CHAT_URL = f"{BASE_URL}/chat/completions"

# glm-4.6：纯文本旗舰对话模型，支持 response_format=json_object，
# 且思考模式可显式关闭（glm-5.3 / glm-5.3-flash 在标准端点强制开启思考，
# 传 thinking.disabled 会报 1210，所以下面会按模型名做区分）。
MODEL = os.environ.get("GLM_MODEL", "glm-4.6")

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_PATH = SCRIPT_DIR / "feedback.txt"
OUTPUT_PATH = SCRIPT_DIR / "out.json"

REQUEST_TIMEOUT = 120          # 秒
MAX_RETRIES = 4                # 针对 429 / 5xx / 网络错误 / JSON 解析失败的重试次数
VALID_URGENCY = ("low", "medium", "high")

SYSTEM_PROMPT = """你是一个客户反馈信息抽取助手。用户会给你一条客户反馈原文，\
你必须只输出一个 JSON 对象，不要输出任何解释文字、不要用 markdown 代码块包裹。

JSON 对象恰好包含以下三个键，不多不少：
{
  "name": "反馈人的姓名。原文中出现的人名，尽量只保留姓名本身（去掉「先生」「女士」「客户」等称谓）；如果原文完全没有提到姓名，填 \\"未知\\"",
  "issue_type": "问题类型，你自己归纳，用简洁的中文短语（4-8 个字），例如 \\"物流延迟\\"、\\"退款问题\\"、\\"产品质量\\"、\\"账号登录异常\\"、\\"客服态度\\"、\\"功能建议\\"",
  "urgency": "紧急程度，只能是 low、medium、high 三者之一（全小写英文）"
}

紧急程度判断参考：
- high：涉及资金损失、服务完全不可用、安全问题、客户明确表达强烈不满或威胁投诉/退货。
- medium：功能受影响但仍可使用、明确诉求且客户表达了催促。
- low：一般咨询、建议、轻微体验问题、表扬中夹带的小意见。"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def build_payload(feedback: str) -> dict:
    """构造 chat/completions 请求体。"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"客户反馈原文：\n{feedback}"},
        ],
        # 智谱平台不支持 json_schema 强约束（传了会被静默忽略），
        # 只有 text / json_object 两种取值，所以结构靠 system prompt 描述 + 客户端校验兜底。
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 512,
    }
    # glm-5.3 / glm-5.3-flash 在标准端点强制开启深度思考，传 disabled 会报 1210。
    if not MODEL.startswith("glm-5.3"):
        payload["thinking"] = {"type": "disabled"}
    return payload


def call_model(session: requests.Session, api_key: str, feedback: str) -> str:
    """调用一次对话补全，返回 message.content 文本。带 429/5xx 指数退避重试。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = build_payload(feedback)
    last_err = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = session.post(
                CHAT_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:      # 网络抖动，值得重试
            last_err = f"网络错误: {exc}"
        else:
            if resp.status_code == 200:
                data = resp.json()
                # 思考模型的思维链在 reasoning_content 字段，正文永远在 content
                return data["choices"][0]["message"].get("content") or ""

            # 4xx（除 429）是配置/参数问题，重试没有意义，直接报错
            if resp.status_code != 429 and resp.status_code < 500:
                raise RuntimeError(
                    f"请求失败 HTTP {resp.status_code}: {resp.text[:500]}"
                )
            # 429（1302 限流 / 1305 过载 / 1113 端点或额度问题）与 5xx：退避重试
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"

        if attempt < MAX_RETRIES - 1:
            sleep_s = (2 ** attempt) + random.uniform(0, 0.5)
            print(f"    [重试 {attempt + 1}/{MAX_RETRIES - 1}] {last_err}；"
                  f"{sleep_s:.1f}s 后重试", file=sys.stderr)
            time.sleep(sleep_s)

    raise RuntimeError(f"多次重试后仍然失败：{last_err}")


def parse_json_object(text: str) -> dict:
    """从模型输出里解析出 JSON 对象，容忍 markdown 代码块和少量多余文字。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("模型返回为空")

    # 去掉 ```json ... ``` 包裹
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 } 之间的内容再试一次
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"输出中找不到 JSON 对象：{text[:200]}")
        obj = json.loads(text[start:end + 1])

    if not isinstance(obj, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    return obj


def normalize(obj: dict) -> dict:
    """规范化为恰好三个键，并校验 urgency 取值。"""
    name = str(obj.get("name") or "").strip() or "未知"

    issue_type = str(obj.get("issue_type") or "").strip() or "其他"

    urgency = str(obj.get("urgency") or "").strip().lower()
    if urgency not in VALID_URGENCY:
        # 常见偏差：模型写了中文或大写
        mapping = {
            "低": "low", "中": "medium", "高": "high",
            "低危": "low", "中危": "medium", "高危": "high",
            "normal": "medium", "urgent": "high", "critical": "high",
        }
        urgency = mapping.get(urgency, "medium")

    return {"name": name, "issue_type": issue_type, "urgency": urgency}


def extract_one(session: requests.Session, api_key: str, feedback: str) -> dict:
    """抽取单条反馈；JSON 解析失败时重试整次调用，最终失败则降级返回占位结果。"""
    last_err = None
    for attempt in range(2):
        try:
            content = call_model(session, api_key, feedback)
            return normalize(parse_json_object(content))
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = exc
            print(f"    解析失败（第 {attempt + 1} 次）：{exc}", file=sys.stderr)
    print(f"    放弃该条，写入占位结果。最后错误：{last_err}", file=sys.stderr)
    return {"name": "未知", "issue_type": "解析失败", "urgency": "medium"}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY。\n"
            "请先执行：export ZHIPUAI_API_KEY=\"你的智谱 API Key\"\n"
            "（Key 获取地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys）",
            file=sys.stderr,
        )
        return 1

    if not INPUT_PATH.exists():
        print(f"错误：找不到输入文件 {INPUT_PATH}", file=sys.stderr)
        return 1

    lines = [
        ln.strip()
        for ln in INPUT_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if not lines:
        print(f"警告：{INPUT_PATH.name} 里没有内容，写出空数组。", file=sys.stderr)
        OUTPUT_PATH.write_text("[]\n", encoding="utf-8")
        return 0

    print(f"共读取 {len(lines)} 条反馈，使用模型 {MODEL} 逐条抽取……")

    results = []
    # 智谱限流按「并发请求数」而非 QPS 计算，这里用串行调用，最稳妥。
    with requests.Session() as session:
        for idx, feedback in enumerate(lines, 1):
            preview = feedback if len(feedback) <= 40 else feedback[:40] + "…"
            print(f"[{idx}/{len(lines)}] {preview}")
            try:
                item = extract_one(session, api_key, feedback)
            except RuntimeError as exc:
                print(f"错误：第 {idx} 条调用失败：{exc}", file=sys.stderr)
                return 1
            print(f"    -> {item['name']} / {item['issue_type']} / {item['urgency']}")
            results.append(item)

    OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"完成，已写出 {OUTPUT_PATH}（{len(results)} 条）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
