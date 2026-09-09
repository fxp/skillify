#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

背景（整理自 bigmodel-cn 技能包与官方文档 docs.bigmodel.cn，2026-09）：
- 套餐 Key 与标准 API Key 是两套隔离的计费体系：必须打 Coding 端点
  https://open.bigmodel.cn/api/coding/paas/v4（比标准端点多一级 /coding）。
  套餐 Key 打标准端点 …/api/paas/v4 必报 429 + 1113「余额不足」，那不是要充值。
- 官方文档口径：套餐只绑定 glm-5.3 / glm-5.3-flash 两个模型；但 2026-09-03
  实测套餐 Key 在 Coding 端点可以直接调视觉模型 glm-4.6v / glm-5v-turbo
  （HTTP 200）。该行为无文档背书、随时可能被收紧，所以本脚本按优先级依次
  尝试多个候选模型，谁先成功用谁，全部失败才下「套餐用不了视觉」的结论。
- Coding 端点存在「静默重路由」（请求 A 实际可能跑 B），所以必须读回响应里
  服务端回显的 model 字段对账，不能只信代码里请求的模型名。

依赖：仅 requests（pip install requests）。
用法：export GLM_CODING_PLAN_API_KEY=<你的套餐 Key> && python3 main.py
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
# 末尾不带 /v1：完整路径是 /api/coding/paas/v4/chat/completions
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_NAME = "invoice.png"
# 候选模型按优先级排列：
#   glm-4.6v / glm-5v-turbo —— 实测（2026-09-03）套餐 Key 在 Coding 端点可用；
#   glm-4.6v-flash          —— 免费视觉模型（探测时恰好 1305 过载，未验证）；
#   glm-5.3-flash           —— 套餐官方模型，文档标注原生多模态、能理解图片。
CANDIDATE_MODELS = ["glm-4.6v", "glm-5v-turbo", "glm-4.6v-flash", "glm-5.3-flash"]
TIMEOUT = 300       # 秒；视觉 + 思考模型出答较慢
MAX_TOKENS = 8192   # 思考 token 也计入 max_tokens，预算给足，避免 content 被思考吃空
PROMPT = (
    "请仔细识别这张发票图片的全部内容，逐项列出关键信息"
    "（例如发票类型/抬头、发票号码、开票日期、购买方与销售方、"
    "金额/税额/价税合计、商品或服务明细等），图片里没有的字段不要编造。"
)


def load_image_as_data_uri():
    """读取脚本同目录下的 invoice.png，编码为 data URI（接口限制单图 ≤5MB）。"""
    path = Path(__file__).resolve().parent / IMAGE_NAME
    if not path.is_file():
        sys.exit("[错误] 找不到图片：%s\n请把 %s 和 main.py 放在同一目录。" % (path, IMAGE_NAME))
    size = path.stat().st_size
    if size > 5 * 1024 * 1024:
        sys.exit("[错误] %s 有 %d 字节，超过接口单图 5MB 上限，请先压缩。" % (IMAGE_NAME, size))
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:%s;base64,%s" % (mime, data)


def parse_error(resp):
    """把失败响应压成一行可读诊断（错误码在响应体 JSON 的 error.code 里）。"""
    try:
        body = resp.json()
        err = body.get("error", body) if isinstance(body, dict) else {}
        code = err.get("code", "?")
        msg = err.get("message", resp.text[:200])
        hint = ""
        if str(code) == "1113":
            hint = "（1113：该模型/能力不在套餐内，或 Key 与端点不匹配）"
        return "HTTP %s code=%s %s %s" % (resp.status_code, code, msg, hint)
    except ValueError:
        return "HTTP %s 非JSON响应: %r" % (resp.status_code, resp.text[:200])


def try_model(model, data_uri, api_key):
    """用指定模型发起一次视觉识别。

    返回 (响应dict或None, 失败原因字符串)。
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
        "max_tokens": MAX_TOKENS,
    }
    print("\n[尝试] model=%s ..." % model)
    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": "Bearer %s" % api_key},
            json=payload,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        return None, "网络异常：%s" % exc

    if resp.status_code != 200:
        return None, parse_error(resp)

    body = resp.json()
    choice = body["choices"][0]
    content = (choice.get("message") or {}).get("content") or ""
    if not content:
        # 典型坑：思考 token 计入 max_tokens，预算被吃光时 content 为空、finish_reason=length
        return None, "HTTP 200 但 content 为空（finish_reason=%s），可能 max_tokens 被思考耗尽" % choice.get("finish_reason")
    return body, ""


def main():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        sys.exit("[错误] 未设置环境变量 %s。\n请先：export %s=<你的套餐 Key>" % (API_KEY_ENV, API_KEY_ENV))

    data_uri = load_image_as_data_uri()
    print("已读取 %s（base64 后 %d 字符）" % (IMAGE_NAME, len(data_uri)))
    print("端点：%s" % CHAT_URL)

    failures = []
    for model in CANDIDATE_MODELS:
        body, reason = try_model(model, data_uri, api_key)
        if body is None:
            print("[失败] %s → %s" % (model, reason))
            failures.append((model, reason))
            continue

        choice = body["choices"][0]
        print("\n===== 模型的回答 =====")
        print(choice["message"]["content"])

        # 对账：Coding 端点可能静默重路由，以服务端回显的 model 字段为准
        served = body.get("model", "?")
        print("\n===== 对账信息 =====")
        print("请求模型     : %s" % model)
        print("实际使用模型 : %s" % served)
        if served and served != model:
            print("[注意] 服务端把你请求的 %s 重路由到了 %s，计费/日志请以实际模型为准。" % (model, served))
        if body.get("id"):
            print("请求 ID      : %s" % body["id"])
        print("finish_reason: %s" % choice.get("finish_reason"))
        usage = body.get("usage") or {}
        if usage:
            print("token 用量   : 输入 %s / 输出 %s / 合计 %s" % (
                usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens")))
        if choice.get("finish_reason") == "length":
            print("[注意] 因 max_tokens 截断，回答可能不完整。")
        return

    # 走到这里说明所有候选都失败了，按失败性质给结论
    print("\n===== 结论 =====")
    for model, reason in failures:
        print("  %s → %s" % (model, reason))

    if all("网络异常" in r for _, r in failures):
        print("全部尝试均为网络异常，尚不能判断套餐是否支持视觉，请先排查网络后重跑。")
    elif all("code=1113" in r for _, r in failures):
        print("所有候选模型均报 1113：可以下结论——当前套餐额度用不了图片输入。")
        print("依据：智谱官方文档口径 Coding Plan 只绑定 glm-5.3 / glm-5.3-flash；")
        print("此前实测 glm-4.6v / glm-5v-turbo 在 Coding 端点可用属于无文档背书的行为，")
        print("可能已被收紧。可行替代：")
        print("  1) 用标准 API Key（按量付费）把 CHAT_URL 换成")
        print("     https://open.bigmodel.cn/api/paas/v4/chat/completions，直接请求 glm-4.6v；")
        print("  2) 继续用套餐额度：官方为 Coding Plan 附带视觉理解 MCP")
        print('     （npx -y "@z_ai/mcp-server"，配 Z_AI_API_KEY + Z_AI_MODE=ZHIPU），')
        print("     在支持 MCP 的工具（如 Claude Code）里使用。")
    else:
        print("存在非 1113 的错误（见上），还不能断定套餐不支持视觉；")
        print("若是 401/403 先检查 Key 是否有效，若是其他错误码请携带上方信息排查后重跑。")
    sys.exit(1)


if __name__ == "__main__":
    main()
