#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

设计依据（docs.bigmodel.cn，核实于 2026-09）：
- 套餐 Key 必须走套餐专用端点 ……/api/coding/paas/v4（比标准 API 多一级 /coding），
  打标准端点 ……/api/paas/v4 会报 429 + 1113“余额不足”，那不是真的要充值。
- 官方文档：所有套餐均支持 GLM-5.3 / GLM-5.3-Flash；其中 GLM-5.3-Flash 是
  “原生多模态模型，能原生理解图片视频”——所以套餐是可以做图片识别的，
  首选模型就是 glm-5.3-flash（glm-5.3 是纯文本旗舰，官方未标图片输入能力）。
- Coding 端点存在“静默换模型”行为（例如 glm-4.6 会被路由到 glm-5.3-flash），
  所以必须读回响应里的 model 字段对账，不能只信代码里请求的名字。
- 本脚本依次尝试：glm-5.3-flash（官方文档背书）→ glm-5v-turbo / glm-4.6v
  （视觉模型，技能包 2026-09 实测套餐 Key 在 Coding 端点可用，官方套餐文档
  未列出，属备选）。只有全部失败才输出“套餐用不了视觉”的结论与实测依据。

用法：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py
"""

import base64
import json
import os
import sys

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_NAME = "invoice.png"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 官方限制：单张图片 ≤ 5MB
REQUEST_TIMEOUT = 180  # 秒

CANDIDATE_MODELS = ("glm-5.3-flash", "glm-5v-turbo", "glm-4.6v")

PROMPT = (
    "请仔细看这张图片：它是什么类型的单据？"
    "请把图中可见的关键信息逐项列出（例如单据类型、抬头/购买方、销售方、"
    "日期、金额、单据号码、商品或服务明细等），看不清的项请标注“无法辨认”。"
)


def fail(msg):
    print("[错误] " + msg, file=sys.stderr)
    sys.exit(1)


def load_image_data_uri(script_dir):
    """把脚本同目录下的 invoice.png 读成 base64 data URI（接口支持的内联图片格式）。"""
    path = os.path.join(script_dir, IMAGE_NAME)
    if not os.path.isfile(path):
        fail("找不到图片：%s（请把 %s 和 main.py 放在同一目录）" % (path, IMAGE_NAME))
    size = os.path.getsize(path)
    if size > MAX_IMAGE_BYTES:
        fail("%s 有 %d 字节，超过接口单图 5MB 上限" % (IMAGE_NAME, size))
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return "data:image/png;base64," + b64


def extract_error(resp):
    """把非 200 响应整理成人能读的错误描述，并附上排查提示。"""
    try:
        body = resp.json()
    except ValueError:
        return "HTTP %d，响应不是 JSON: %s" % (resp.status_code, resp.text[:300])
    err = body.get("error") or body
    code = str(err.get("code", body.get("code", "?")))
    msg = err.get("message", err.get("msg", json.dumps(body, ensure_ascii=False)[:300]))
    hint = ""
    if code == "1113":
        hint = "（1113 三种成因：端点打错 / 能力不在套餐 / 模型不在套餐。本脚本已用套餐端点，若连 glm-5.3-flash 都报此错，则是额度耗尽或该能力当前被移出套餐）"
    elif code == "1210":
        hint = "（1210：参数或模型不支持——发生在图片请求上，多半是该模型不支持图片输入）"
    elif resp.status_code in (401, 403):
        hint = "（鉴权失败：请检查 %s 是否为套餐 Key 本身）" % API_KEY_ENV
    return "HTTP %d, code=%s, message=%s %s" % (resp.status_code, code, msg, hint)


def try_model(model, data_uri, api_key):
    """用指定模型发一次带图片的对话请求。返回 (响应dict, None) 或 (None, 错误描述)。"""
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
        # Coding 端点实测接受并真正关闭思考（标准端点会报 1210）；
        # 关掉可避免思考 token 挤占输出预算、出现空回复。
        "thinking": {"type": "disabled"},
        "max_tokens": 4096,
        "stream": False,
    }
    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": "Bearer " + api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        return None, "网络异常：%s" % e
    if resp.status_code != 200:
        return None, extract_error(resp)

    data = resp.json()
    # HTTP 200 也要校验业务结果：finish_reason=length 时 content 可能是空串
    choices = data.get("choices") or [{}]
    choice = choices[0]
    finish = choice.get("finish_reason")
    content = (choice.get("message") or {}).get("content") or ""
    if finish != "stop" or not content.strip():
        return None, (
            "HTTP 200 但结果异常：finish_reason=%r，content=%r；"
            "（若为 length，是输出预算被截断，可调大 max_tokens）"
            % (finish, content[:100])
        )
    return data, None


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        fail("请先设置环境变量 %s（GLM Coding Plan 套餐 Key）" % API_KEY_ENV)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_uri = load_image_data_uri(script_dir)
    print("已载入 %s（%d 字节），套餐端点：%s" % (IMAGE_NAME, len(data_uri), CHAT_URL))

    failures = []
    for model in CANDIDATE_MODELS:
        print("\n—— 正在尝试模型 %s ……" % model)
        data, err = try_model(model, data_uri, api_key)
        if data is not None:
            content = data["choices"][0]["message"]["content"]
            served = data.get("model", "?")
            print("\n=== 模型回答 ===")
            print(content)
            print("\n=== 对账信息 ===")
            print("请求模型           : %s" % model)
            print("服务端实际使用模型 : %s（来自响应 model 字段）" % served)
            if served != model:
                print("⚠ 注意：服务端把你请求的 %s 静默路由到了 %s，计费/日志以服务端为准" % (model, served))
            print("finish_reason      : %s" % data["choices"][0].get("finish_reason"))
            usage = data.get("usage")
            if usage:
                print("token 用量         : %s" % json.dumps(usage, ensure_ascii=False))
            return
        print("  失败：%s" % err)
        failures.append((model, err))

    print("\n" + "=" * 60)
    print("结论：已依次实际尝试 " + "、".join(m for m, _ in failures) +
          "（套餐专用端点 /api/coding/paas/v4，带图片输入），全部失败。")
    print("依据（逐条实测错误）：")
    for model, err in failures:
        print("  - %s：%s" % (model, err))
    print("因此这把套餐 Key 当前无法完成图片识别。请对照 docs.bigmodel.cn/cn/coding-plan/faq")
    print("排查；若确认视觉能力不在套餐内，需改用标准 API Key 走 /api/paas/v4 的")
    print("视觉模型（如 glm-4.6v、glm-5v-turbo）。")
    sys.exit(2)


if __name__ == "__main__":
    main()
