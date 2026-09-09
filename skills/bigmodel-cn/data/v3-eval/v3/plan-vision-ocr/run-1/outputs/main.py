#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 里的内容。

关键背景（来自 bigmodel-cn 技能包，实测于 2026-09）：
- 套餐 Key 与标准 API Key 是两套隔离体系：套餐 Key 只能打 Coding 端点
  https://open.bigmodel.cn/api/coding/paas/v4/*，打标准端点必报 1113。
- 官方文档只承诺套餐支持 glm-5.3 / glm-5.3-flash（图像理解靠附赠的视觉
  MCP），但实测视觉模型 glm-4.6v、glm-5v-turbo 在 Coding 端点直接可用，
  且 chat 文档把 glm-5.3-flash 也列为接受图片输入的模型。因此本脚本按
  glm-5.3-flash → glm-4.6v → glm-5v-turbo 依次真试，只有全部失败才得出
  "套餐用不了视觉"的结论，并附上每次失败的报错证据。
- 服务端可能静默更换模型（如 glm-4.6 被换成 glm-5.3-flash），所以必须
  读回响应里的 model 字段对账，不能信请求里写了什么。
- 思考 token 计入 max_tokens：finish_reason == "length" 说明正文被截断，
  按"加倍 max_tokens + 关闭思考"重试一次（thinking:disabled 仅在 Coding
  端点被接受，标准端点会报 1210）。
"""

import base64
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
# Coding Plan 专用端点（注意比标准端点多一级 /coding；套餐 Key 打
# /api/paas/v4 会报 429 + 1113 "余额不足"，那是端点错了，不是真欠费）
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
# 依次尝试的候选模型：先官方承诺在套餐内的 glm-5.3-flash，
# 再实测在套餐端点可用的两个视觉模型
CANDIDATE_MODELS = ["glm-5.3-flash", "glm-4.6v", "glm-5v-turbo"]
# 思考 token 也计入 max_tokens，预算给足以避免 finish_reason=length
MAX_TOKENS = 8192
TIMEOUT_SECONDS = 300
PROMPT = (
    "请仔细识别这张图片里的全部内容并逐项描述。"
    "如果这是发票/票据/收据，请列出关键信息：发票名称（类型）、开票方、"
    "受票方、金额（价税合计）、开票日期、发票号码等；"
    "如果不是发票，就如实描述图片里有什么。"
)


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def load_image_data_uri(path: Path) -> str:
    if not path.is_file():
        die(f"找不到图片：{path}（请把 invoice.png 放在 main.py 同目录下）")
    raw = path.read_bytes()
    print(f"图片：{path}（{len(raw) / 1024:.0f} KB）")
    if len(raw) > 5 * 1024 * 1024:
        # chat/completions 的 base64 内联单图上限约 5MB
        print("[警告] 图片超过 5MB 内联上限，可能被服务端拒绝", file=sys.stderr)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def clean_content(text: str) -> str:
    """视觉模型的 content 里可能夹带思考标签和文本边界标签，展示前剥掉。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
    return text.strip()


def parse_api_error(resp) -> str:
    """尽量从响应体里抠出错误码和报错信息，作为失败证据返回。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应体不是 JSON：{resp.text[:200]!r}"
    err = body.get("error") or {}
    code = err.get("code") or body.get("code")
    msg = err.get("message") or body.get("msg") or resp.text[:200]
    return f"HTTP {resp.status_code} 错误码 {code}：{msg}"


def call_once(api_key, model, image_uri, max_tokens, disable_thinking):
    """单次调用。返回 (data, None) 或 (None, 证据字符串)。

    网络异常和疑似瞬时报错（5xx、非 1113 的 429）退避重试；1113 属于
    "端点/能力/模型不在套餐内"的确定性失败，直接返回好让外层换模型。
    """
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_uri}},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    headers = {"Authorization": f"Bearer {api_key}"}

    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(CHAT_URL, headers=headers, json=payload,
                                 timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_err = f"网络错误：{exc}"
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 200:
            try:
                return resp.json(), None
            except ValueError:
                return None, f"HTTP 200 但响应体不是 JSON：{resp.text[:200]!r}"
        last_err = parse_api_error(resp)
        transient = resp.status_code >= 500 or (
            resp.status_code == 429 and "1113" not in last_err)
        if not transient:
            return None, last_err
        time.sleep(3 * (attempt + 1))
    return None, last_err


def run_model(api_key, model, image_uri):
    """跑一个候选模型。返回 (data, None) 或 (None, 证据字符串)。"""
    data, err = call_once(api_key, model, image_uri, MAX_TOKENS,
                          disable_thinking=False)
    if err:
        return None, err
    if not data.get("choices"):
        return None, f"响应 200 但没有 choices：{json.dumps(data, ensure_ascii=False)[:300]}"
    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content") or ""
    # 撞上"思考吃光预算"（length 截断 / 正文为空）时补救一次：
    # max_tokens 翻倍并关闭思考；补救失败则保留第一次的结果
    if choice.get("finish_reason") == "length" or not content.strip():
        data_retry, err_retry = call_once(api_key, model, image_uri,
                                          MAX_TOKENS * 2, disable_thinking=True)
        if not err_retry and data_retry.get("choices"):
            data = data_retry
    return data, None


def report(requested_model, data):
    choice = data["choices"][0]
    content = clean_content((choice.get("message") or {}).get("content") or "")
    finish_reason = choice.get("finish_reason")

    print("\n===== 模型回答 =====")
    print(content or f"（模型未返回正文，finish_reason={finish_reason}）")
    if finish_reason == "length":
        print("[警告] finish_reason=length，回答可能被截断")

    print("\n===== 对账信息 =====")
    used_model = data.get("model", "<响应里没有 model 字段>")
    print(f"请求模型：{requested_model}")
    print(f"服务端实际使用模型：{used_model}")
    if used_model != requested_model:
        print(f"[警告] 服务端把 {requested_model} 静默换成了 {used_model}，"
              f"计费和能力以实际模型为准")
    request_id = data.get("request_id") or data.get("id")
    if request_id:
        print(f"request_id：{request_id}")
    if data.get("usage"):
        print(f"用量：{json.dumps(data['usage'], ensure_ascii=False)}")


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        die(f"请先设置环境变量 {API_KEY_ENV}（GLM Coding Plan 套餐 Key）")

    image_uri = load_image_data_uri(Path(__file__).resolve().parent / "invoice.png")
    print(f"端点：{CHAT_URL}")
    print(f"候选模型（按序尝试）：{' → '.join(CANDIDATE_MODELS)}")

    failures = []
    for model in CANDIDATE_MODELS:
        print(f"\n==> 尝试模型 {model} …")
        data, err = run_model(api_key, model, image_uri)
        if data:
            report(model, data)
            return
        failures.append((model, err))
        print(f"    失败：{err}")

    print("\n[结论] 所有候选模型都失败：当前这把 Coding Plan Key 无法完成图片理解。"
          "逐项证据：")
    for model, err in failures:
        print(f"  - {model}: {err}")
    print(
        "排查建议（按 端点 → 能力 → 模型 的顺序）：\n"
        "  1. 报 1113 多为端点/能力/模型不在套餐内，不是欠费，不要去充值；\n"
        "  2. 套餐的图像理解官方路径是附赠的视觉理解 MCP（npx -y @z_ai/mcp-server）；\n"
        "  3. 要在代码里直接调视觉 chat/completions，需标准 API Key 走 "
        "https://open.bigmodel.cn/api/paas/v4。"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
