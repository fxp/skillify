#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别脚本同目录下 invoice.png 的内容。

依据（bigmodel-cn 技能包 references/coding-plan.md、references/chat.md、
references/models.md，并对照 docs.bigmodel.cn/cn/coding-plan/overview 核实，2026-09）：

- 套餐 Key 与标准 API Key 不通用：套餐必须打
  https://open.bigmodel.cn/api/coding/paas/v4/chat/completions（比标准端点多一级
  /coding，且后面没有 /v1）。套餐 Key 打标准端点必报 1113「余额不足」。
- 官方文档只承诺套餐支持 glm-5.3 / glm-5.3-flash，其中 glm-5.3-flash 是原生
  多模态模型（可直接理解图片）；官方页面未把任何视觉模型列入套餐。
- 技能包 2026-09-03 实测：套餐 Key 在 Coding 端点请求 glm-4.6v / glm-5v-turbo
  返回 200 原样可用，但无官方背书。官方文档与实测结论冲突，所以本脚本按
  「官方在册 → 实测可用」的顺序逐个尝试，先试过再下结论。
- Coding 端点存在静默重路由（请求 glm-4.6 实际跑 glm-5.3-flash），因此无论
  成败都打印服务端回显的 model 字段 / 完整错误码，供对账使用。

注意：官方条款规定套餐「仅限在官方支持的指定工具与产品环境中使用」，自写脚本
调用 Coding 端点技术上可行，但属于条款之外的用法，额度扣减行为以官方为准；
生产环境请改用标准 API Key 走 …/api/paas/v4。

用法：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py
"""

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
# 套餐专用 Base URL：https://open.bigmodel.cn/api/coding/paas/v4（无 /v1 这一级）
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_NAME = "invoice.png"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # chat/completions 单图上限 5M
MAX_TOKENS = 8192  # 思考 token 计入 max_tokens，给足预算避免内容被截空
TIMEOUT = 180

# 依次尝试的模型：先官方在册的原生多模态模型，再技能包实测可用的视觉模型
CANDIDATE_MODELS = [
    ("glm-5.3-flash", "套餐官方在册，原生多模态"),
    ("glm-4.6v", "技能包实测套餐端点可用（无官方背书）"),
    ("glm-5v-turbo", "技能包实测套餐端点可用（无官方背书）"),
]

PROMPT = (
    "这是一张发票图片。请仔细识别图中内容，用中文列出关键信息"
    "（例如发票名称/抬头、开票方、受票方、金额、日期、发票号等），"
    "看不清或不确定的字段请注明。"
)


def load_image_data_uri() -> str:
    """读取脚本同目录下的 invoice.png，编码成 base64 data URI（内联传图）。"""
    path = Path(__file__).resolve().parent / IMAGE_NAME
    if not path.is_file():
        sys.exit(f"[错误] 找不到图片：{path}（请把 {IMAGE_NAME} 放到和 main.py 同一目录）")
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        sys.exit(f"[错误] {IMAGE_NAME} 共 {len(data)} 字节，超过接口单图 5M 上限")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def describe_error(resp: requests.Response) -> str:
    """把失败响应整理成一行可读证据（HTTP 状态码 + 平台错误码 + message）。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应非 JSON：{resp.text[:200]!r}"
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    code = err.get("code")
    msg = err.get("message") or err.get("msg")
    hint = ""
    if str(code) == "1113":
        hint = "（1113 对套餐 Key 通常意味着该模型/能力不在套餐范围内，不是要充值）"
    return f"HTTP {resp.status_code}，错误码 {code}：{msg}{hint}"


def try_model(model: str, image_data_uri: str, api_key: str):
    """用指定模型发起一次视觉识别。返回 (是否成功, 成功时为结果 dict / 失败时为原因)。"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            }
        ],
        "max_tokens": MAX_TOKENS,
    }
    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        return False, f"网络请求失败：{exc}"

    if resp.status_code != 200:
        return False, describe_error(resp)

    try:
        data = resp.json()
    except ValueError:
        return False, f"HTTP 200 但响应不是 JSON：{resp.text[:200]!r}"

    choices = data.get("choices") or []
    if not choices:
        return False, f"HTTP 200 但无 choices：{json.dumps(data, ensure_ascii=False)[:300]}"
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")
    if not content:
        # 已知陷阱：思考 token 计入 max_tokens，预算被吃光时 content 为空串
        return False, (
            f"HTTP 200 但 content 为空（finish_reason={finish_reason}，"
            "典型原因是思考耗尽 max_tokens 预算）"
        )
    return True, {"data": data, "content": content, "finish_reason": finish_reason}


def report_success(requested_model: str, result: dict) -> None:
    data = result["data"]
    actual_model = data.get("model", "<响应中无 model 字段>")
    print("\n================ 识别结果 ================")
    print(result["content"])
    print("\n================ 对账信息 ================")
    print(f"请求模型：{requested_model}")
    print(f"服务端实际使用模型：{actual_model}")
    if actual_model != requested_model:
        print("⚠️ 两者不一致：Coding 端点会把部分模型名静默重路由（如 glm-4.6 → glm-5.3-flash），")
        print("  对账请以服务端回显的 model 字段为准。")
    print(f"finish_reason：{result['finish_reason']}")
    if data.get("id"):
        print(f"响应 id：{data['id']}")
    usage = data.get("usage")
    if usage:
        print(f"token 用量：{json.dumps(usage, ensure_ascii=False)}")


def report_failure(failures) -> None:
    print("\n================ 结论 ================")
    print("已按顺序真实尝试以下模型，全部失败，未能用套餐额度完成视觉识别：")
    for model, reason in failures:
        print(f"  - {model}：{reason}")
    print()
    print("依据与建议：")
    print("  1. 官方文档（docs.bigmodel.cn/cn/coding-plan/overview）只承诺套餐支持")
    print("     glm-5.3 / glm-5.3-flash，未把任何视觉模型列入套餐模型清单；")
    print("  2. 官方为套餐提供的视觉能力入口是「视觉理解 MCP」（配合指定编码工具），")
    print("     而非直接调 chat/completions 传图；")
    print("  3. 若上方错误码为 1113：端点已按套餐要求配置（…/api/coding/paas/v4），")
    print("     此时 1113 表示该模型/能力不在套餐范围内，不是账户需要充值；")
    print("  4. 要在自有代码里做图片识别，请使用标准 API Key（如 ZHIPUAI_API_KEY）走")
    print("     https://open.bigmodel.cn/api/paas/v4，模型选 glm-4.6v 等视觉模型。")
    sys.exit(1)


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"[错误] 未设置环境变量 {API_KEY_ENV}（GLM Coding Plan 套餐 Key）")

    print(f"提示：官方条款限定套餐在指定编码工具内使用，自写脚本调用属条款外用法，额度扣减以官方为准。")
    image_data_uri = load_image_data_uri()
    failures = []

    for idx, (model, note) in enumerate(CANDIDATE_MODELS, 1):
        print(f"[{idx}/{len(CANDIDATE_MODELS)}] 尝试模型 {model}（{note}）……", flush=True)
        ok, result = try_model(model, image_data_uri, api_key)
        if ok:
            report_success(model, result)
            return
        print(f"    失败：{result}", flush=True)
        failures.append((model, result))

    report_failure(failures)


if __name__ == "__main__":
    main()
