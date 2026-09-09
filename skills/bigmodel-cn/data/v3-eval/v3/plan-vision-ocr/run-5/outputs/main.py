#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

关键依据（官方文档 docs.bigmodel.cn + bigmodel-cn 技能包 2026-09 实测）：
- 套餐 Key 与标准 API Key 不通用，必须走套餐专用端点
  https://open.bigmodel.cn/api/coding/paas/v4（路径里没有 /v1 这一级）；
  套餐 Key 打标准端点 /api/paas/v4 必报 429 + 1113「余额不足」。
- 官方文档只承诺套餐支持 glm-5.3 / glm-5.3-flash，图像理解官方口径走套餐附赠的
  MCP 工具；但实测视觉模型 glm-4.6v、glm-5v-turbo 在套餐端点原样可用。
  因此本脚本按候选列表逐个「真试」，全部失败才下「套餐用不了视觉」的结论。
- 套餐端点存在静默换模型（如 glm-4.6 -> glm-5.3-flash），所以必须读回响应里的
  model 字段对账，不能假设请求什么模型就跑什么模型。

只用 requests + 标准库。运行：python3 main.py
"""

import base64
import json
import os
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CODING_CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 套餐端点上值得真试一把的模型，按优先级排列：
#   glm-4.6v / glm-5v-turbo —— 实测在套餐端点可用的视觉模型
#   glm-5.3-flash           —— 官方套餐内模型，文档标注其原生多模态（能理解图片）
#   glm-4.6v-flash          —— 免费视觉模型，兜底
VISION_MODEL_CANDIDATES = [
    "glm-4.6v",
    "glm-5v-turbo",
    "glm-5.3-flash",
    "glm-4.6v-flash",
]

MAX_TOKENS = 4096  # 思考 token 也计入 max_tokens，预算给足，避免 finish_reason=length
TIMEOUT_SECONDS = 300
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 官方限制：单图 ≤ 5MB

PROMPT = (
    "请仔细识别这张图片中的全部内容，尽量完整地转写其中的文字信息"
    "（例如发票抬头、开票日期、购买方与销售方、金额、税额、发票编号等；"
    "如果图片并不是发票，就如实描述图片内容）。"
)


def find_image():
    """定位 invoice.png：优先脚本同目录，其次当前工作目录。"""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        path = base / "invoice.png"
        if path.is_file():
            return path
    sys.exit(
        "找不到 invoice.png（请把它放到和 main.py 同一个目录，"
        f"已尝试：{Path(__file__).resolve().parent / 'invoice.png'}）"
    )


def load_image_data_uri(path):
    """把图片读成 data URI（多模态接口的 image_url 支持 base64 输入）。"""
    size = path.stat().st_size
    if size > IMAGE_MAX_BYTES:
        sys.exit(f"图片 {size} 字节，超过官方单图 5MB 限制，请先压缩")
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}", size


def extract_error(body):
    """从响应体里尽量挖出错误码和描述，兼容 {"error":{...}} 与顶层字段两种形态。"""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return f"code={err.get('code')} message={err.get('message')}"
        parts = [f"{k}={body[k]}" for k in ("code", "message", "msg", "error") if k in body]
        if parts:
            return " ".join(parts)
        return json.dumps(body, ensure_ascii=False)[:300]
    return str(body)[:300]


def call_vision_model(model, data_uri, api_key, max_tokens):
    """在套餐端点上用指定模型做一次图片识别调用。

    返回 dict：ok / http / error / content / served_model / finish_reason。
    不抛异常，失败信息都放在 error 里，由调用方决定换下一个模型。
    """
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(
            CODING_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return {"ok": False, "http": 0, "error": f"网络异常: {exc}",
                "content": "", "served_model": "", "finish_reason": ""}

    if resp.status_code != 200:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        return {"ok": False, "http": resp.status_code, "error": extract_error(body),
                "content": "", "served_model": "", "finish_reason": ""}

    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "http": 200, "error": f"响应不是 JSON: {resp.text[:300]}",
                "content": "", "served_model": "", "finish_reason": ""}

    choices = data.get("choices") or []
    if not choices:
        return {"ok": False, "http": 200, "error": f"响应里没有 choices: {extract_error(data)}",
                "content": "", "served_model": data.get("model", ""), "finish_reason": ""}

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):  # 个别模型可能返回结构化 content，兜底转成可打印文本
        content = json.dumps(content, ensure_ascii=False) if content else ""
    return {
        "ok": True,
        "http": 200,
        "error": None,
        "content": content,
        "served_model": data.get("model", ""),
        "finish_reason": choices[0].get("finish_reason", ""),
    }


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"请先设置环境变量 {API_KEY_ENV}（GLM Coding Plan 套餐 Key）")

    image_path = find_image()
    data_uri, size = load_image_data_uri(image_path)
    print(f"已加载 {image_path.name}（{size} 字节），套餐端点：{CODING_CHAT_URL}")
    print(f"按候选列表逐个真试：{' -> '.join(VISION_MODEL_CANDIDATES)}\n")

    failures = []
    for model in VISION_MODEL_CANDIDATES:
        print(f"--- 尝试模型 {model} ---")
        result = call_vision_model(model, data_uri, api_key, MAX_TOKENS)

        if result["ok"] and result["finish_reason"] == "length":
            # 思考 token 计入 max_tokens：被截断就翻倍预算重试一次，拿到完整结果再交付
            print("    输出被 max_tokens 截断，翻倍预算重试一次……")
            result = call_vision_model(model, data_uri, api_key, MAX_TOKENS * 2)

        if not result["ok"]:
            print(f"    失败：HTTP {result['http']} {result['error']}")
            failures.append((model, result["http"], result["error"]))
            continue

        if not result["content"]:
            # 200 但空内容（且已排除截断）：当作失败，换下一个模型，不交付半截结果
            reason = result["finish_reason"] or "未知"
            print(f"    失败：HTTP 200 但返回空内容（finish_reason={reason}）")
            failures.append((model, 200, f"空内容 finish_reason={reason}"))
            continue

        print("    成功。\n")
        print("=== 模型回答 ===")
        print(result["content"])
        if result["finish_reason"] == "length":
            print("\n（注意：finish_reason=length，以上内容可能被截断）")
        print("\n=== 对账信息（以服务端响应为准） ===")
        served = result["served_model"]
        print(f"请求的模型: {model}")
        print(f"服务端实际使用的模型: {served or '（响应里没有 model 字段）'}")
        if result["finish_reason"]:
            print(f"finish_reason: {result['finish_reason']}")
        if served and served != model:
            print(
                f"注意：服务端把 {model} 静默换成了 {served}（套餐端点存在自动路由，"
                f"计费与能力都按实际模型算，对账请以 {served} 为准）"
            )
        return

    # 走到这里说明所有候选模型都真试过且全部失败，才下结论
    print()
    print("=" * 62)
    print("结论：这把 GLM Coding Plan 套餐 Key 在 chat/completions 接口上无法完成图片识别。")
    print("依据（每一次真实尝试的结果）：")
    for model, http, error in failures:
        print(f"  - {model}: HTTP {http}, {error}")
    print()
    print("说明：")
    print(f"  1. 已确认走的是套餐专用端点 {CODING_CHAT_URL}，")
    print("     所以这里的 1113 不是「打错端点」，而是「视觉模型/能力不在套餐内」。")
    print("  2. 官方文档（docs.bigmodel.cn/cn/coding-plan/overview）只承诺套餐支持")
    print("     glm-5.3 / glm-5.3-flash，图像理解官方口径走套餐附赠的 MCP 工具")
    print('     （npx -y "@z_ai/mcp-server"，视觉理解走套餐额度）。')
    print("  3. 替代方案：用标准 API Key（ZHIPUAI_API_KEY）走")
    print("     https://open.bigmodel.cn/api/paas/v4 调 glm-4.6v 等视觉模型。")
    sys.exit(1)


if __name__ == "__main__":
    main()
