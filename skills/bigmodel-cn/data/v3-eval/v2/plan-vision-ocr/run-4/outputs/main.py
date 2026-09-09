#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

要点（依据 bigmodel-cn 技能包整理的官方文档与 2026-09 实测结论）：
- 套餐 Key 必须走 Coding 端点 https://open.bigmodel.cn/api/coding/paas/v4；
  打标准端点 /api/paas/v4 会报 429 + 1113「余额不足」，那不是真的缺钱。
- 官方口径套餐只含 glm-5.3 / glm-5.3-flash，其中 glm-5.3-flash 原生支持
  图片输入（多模态 content 数组 + image_url），首选它。
- 实测视觉模型 glm-5v-turbo / glm-4.6v 在 Coding 端点用套餐 Key 也可用，
  但官方文档未列入套餐，作为备选依次尝试。
- Coding 端点会把请求的模型静默重路由成别的模型（请求 A 实际跑 B），
  因此必须读回响应体里的 model 字段对账，不能只看请求里写了什么。

仅依赖 requests + 标准库。用法：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_PATH = Path(__file__).resolve().parent / "invoice.png"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 接口限制：单图 ≤5MB，jpg/png/jpeg
TIMEOUT = (30, 300)  # (连接超时, 读取超时)；带图请求较慢，读取放宽到 5 分钟

# 依次尝试的模型：首选官方套餐内的多模态 glm-5.3-flash，
# 备选为实测可用、但官方未列入套餐的视觉模型。
CANDIDATE_MODELS = ["glm-5.3-flash", "glm-5v-turbo", "glm-4.6v"]

PROMPT = (
    "请识别这张图片（invoice.png）里的内容：如果是一张发票/票据，"
    "请把标题、开票方、收款方、金额、日期等关键字段列出来；"
    "如果不是发票，就如实描述图片里的内容。"
)


def load_image_as_data_uri() -> str:
    """读取本地图片并编码为 data URI（接口支持 Base64 直传，无需先上传）。"""
    if not IMAGE_PATH.is_file():
        sys.exit(f"[错误] 找不到图片：{IMAGE_PATH}（请把 invoice.png 放在 main.py 同目录下）")
    size = IMAGE_PATH.stat().st_size
    if size > MAX_IMAGE_BYTES:
        sys.exit(f"[错误] 图片过大：{size} 字节，超过单图 5MB 上限，请先压缩")
    mime = mimetypes.guess_type(str(IMAGE_PATH))[0] or "image/png"
    b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def extract_error(resp) -> str:
    """把 HTTP 错误响应压成一行可读信息，尽量带出业务错误码（如 1113）。"""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}，响应非 JSON: {resp.text[:200]!r}"
    err = body.get("error")
    if isinstance(err, dict):
        return f"HTTP {resp.status_code}，code={err.get('code')}，message={err.get('message')}"
    if err:
        return f"HTTP {resp.status_code}，error={err}"
    return f"HTTP {resp.status_code}，body={str(body)[:200]}"


def try_model(model: str, api_key: str, image_uri: str):
    """用指定模型发一次带图请求。成功返回 (回答文本, 对账信息)；失败返回 (None, 错误说明)。"""
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
        "stream": False,
    }
    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        return None, f"网络/超时异常: {exc}"

    if resp.status_code != 200:
        return None, extract_error(resp)

    try:
        data = resp.json()
    except ValueError:
        return None, f"HTTP 200 但响应非 JSON: {resp.text[:200]!r}"

    choices = data.get("choices") or []
    if not choices:
        # 防御：个别接口 200 + body.code 报错，不能只看 HTTP 状态码
        return None, f"HTTP 200 但无 choices（code={data.get('code')}，body={str(data)[:200]}）"

    message = choices[0].get("message") or {}
    text = message.get("content")
    finish = choices[0].get("finish_reason")

    # 已知坑：思考 token 计入 max_tokens，预算被吃光时 content 为空串、
    # finish_reason=length——空内容先看 finish_reason，别急着判能力不可用
    if not text:
        reason = message.get("reasoning_content") or ""
        return None, (
            f"content 为空（finish_reason={finish}）。"
            f"若为 length 说明思考/输出预算耗尽，可加大 max_tokens 重试；"
            f"reasoning_content 长度={len(reason)}"
        )

    info = {
        "requested": model,
        "served": data.get("model"),  # 服务端实际使用的模型，对账以它为准
        "finish_reason": finish,
        "usage": data.get("usage") or {},
    }
    return text, info


def report_success(text: str, info: dict) -> None:
    print("========== 模型回答 ==========")
    print(text)
    print("==============================")
    print()
    print("========== 对账信息 ==========")
    print(f"请求模型       : {info['requested']}")
    print(f"服务端实际模型 : {info['served']}   ← 以响应体 model 字段为准")
    if info["served"] and info["served"] != info["requested"]:
        print(f"⚠ 注意：实际模型与请求不一致（Coding 端点存在静默重路由），计费/日志请按 {info['served']} 对账。")
    print(f"finish_reason  : {info['finish_reason']}")
    usage = info["usage"]
    if usage:
        print(
            f"usage          : prompt={usage.get('prompt_tokens')}, "
            f"completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')}"
        )
    print("==============================")
    print()
    print("[提醒] 官方条款限定套餐仅在指定编码工具环境中使用；脚本直调技术上可行，但是否计套餐额度以官方为准。")


def report_failure(failures) -> None:
    print("========== 结论：本次实测未能用套餐额度完成图片识别 ==========")
    print("已按优先级真实尝试以下模型，全部失败：")
    for model, err in failures:
        print(f"  - {model}: {err}")
    print()
    print("判读依据：")
    print("  * 429 + 1113「余额不足」在套餐场景有三种成因：端点错 / 能力不在套餐 / 模型不在套餐。")
    print("    本脚本已固定走正确的 Coding 端点（…/api/coding/paas/v4），若仍报 1113，")
    print("    说明对应模型或视觉能力不在当前套餐权益内——这是「套餐用不了视觉」的证据。")
    print("  * 官方文档口径：套餐仅含 glm-5.3 / glm-5.3-flash；套餐的视觉理解官方路径是附赠的")
    print('    视觉 MCP（npx -y "@z_ai/mcp-server"，Z_AI_API_KEY 填套餐 Key），')
    print("    或者改用标准 API Key 走 https://open.bigmodel.cn/api/paas/v4 调 glm-4.6v / glm-ocr。")


def main() -> int:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"[错误] 未设置环境变量 {API_KEY_ENV}，请先 export 后再运行。")

    image_uri = load_image_as_data_uri()
    print(f"[信息] 图片: {IMAGE_PATH}（base64 后 {len(image_uri)} 字符）")
    print(f"[信息] 端点: {CHAT_URL}（Coding Plan 专用端点，勿改成 /api/paas/v4）")
    print()

    failures = []
    for i, model in enumerate(CANDIDATE_MODELS, 1):
        tag = f"[{i}/{len(CANDIDATE_MODELS)}] {model}"
        print(f"{tag} 请求中……")
        text, info = try_model(model, api_key, image_uri)
        if text is None:
            print(f"{tag} 失败：{info}")
            print()
            failures.append((model, info))
            continue
        print(f"{tag} 成功")
        print()
        report_success(text, info)
        return 0

    report_failure(failures)
    return 1


if __name__ == "__main__":
    sys.exit(main())
