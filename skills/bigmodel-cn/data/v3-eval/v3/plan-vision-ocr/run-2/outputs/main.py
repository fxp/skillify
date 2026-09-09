#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容，并打印对账信息。

用法：
    export GLM_CODING_PLAN_API_KEY=<你的套餐 Key>
    python3 main.py

设计要点（依据 bigmodel-cn 技能包实测记录 + docs.bigmodel.cn 官方文档，2026-09）：
- 套餐 Key 必须打套餐专属端点 https://open.bigmodel.cn/api/coding/paas/v4，
  打标准端点 …/api/paas/v4 必报 1113"余额不足"——那是端点错，不是真没钱，不要去充值。
- 官方明文套餐只保证 glm-5.3 / glm-5.3-flash（glm-5.3-flash 为原生多模态），
  套餐视觉能力的官方交付方式是附赠的视觉 MCP；但实测 glm-4.6v、glm-5v-turbo
  也能直接在套餐端点跑通（无文档背书）。因此按候选链逐个真试，不预设"套餐不支持视觉"，
  只有全部失败才下结论，并附上每次尝试的错误码作为依据。
- 服务端可能静默更换模型（如 glm-4.6 → glm-5.3-flash），对账必须读响应里回显的 model 字段，
  不能只看请求参数。
- 思考 token 计入 max_tokens：finish_reason=length 时加大预算并关闭思考重试一次，
  不把半截结果当失败丢掉。
"""

import base64
import os
import re
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
# 套餐专属端点：比标准 API 多一级 /coding；路径里没有 /v1，不要再拼
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
TIMEOUT = 180  # 秒，图片理解比纯文本慢
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 平台限制：单图 <=5MB，<=6000x6000，jpg/png/jpeg

# 视觉候选链：谁成功用谁，全部失败才宣告"套餐用不了视觉"
# 1) glm-5.3-flash：官方明文所有套餐档位支持，且是原生多模态模型，最有背书的一条路
# 2) glm-4.6v / glm-5v-turbo：官方文档未列入套餐，但 2026-09-03 实测在套餐端点可用
CANDIDATE_MODELS = ["glm-5.3-flash", "glm-4.6v", "glm-5v-turbo"]

# 撞上这些错误码说明"当前模型这条路走不通"，换下一个候选继续，而不是直接放弃：
#   1113 能力/模型不在套餐（或端点错，本脚本端点已排除）
#   1210 参数或模型名非法
#   1305 模型过载
FALLBACK_ERROR_CODES = {"1113", "1210", "1305"}


class ApiError(Exception):
    """服务端业务错误，携带 HTTP 状态与平台错误码，用于区分"换模型重试"和"直接终止"。"""

    def __init__(self, status, code, message):
        super().__init__(f"HTTP {status}, code={code}, message={message}")
        self.status = status
        self.code = str(code)
        self.message = str(message)


def load_image_data_uri():
    """读取脚本同目录下的 invoice.png，编码成 data URI（平台支持 base64 内联图片）。"""
    img_path = Path(__file__).resolve().parent / "invoice.png"
    if not img_path.is_file():
        sys.exit(f"找不到图片：{img_path}（请把 invoice.png 放在脚本同目录下）")
    raw = img_path.read_bytes()
    if not raw:
        sys.exit(f"图片是空文件：{img_path}")
    if len(raw) > MAX_IMAGE_BYTES:
        sys.exit(f"图片 {len(raw) / 1024 / 1024:.1f}MB 超过平台单图 5MB 上限，请先压缩")
    # 按后缀推断 MIME（平台支持 jpg/jpeg/png），兜底按文件名约定的 png
    mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return "data:{};base64,{}".format(mime, base64.b64encode(raw).decode("ascii"))


def strip_think_tags(text):
    """部分视觉模型会把 <think>...</think> 思考链直接混在 content 里，打印前剥掉。"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def chat(model, data_uri, api_key, max_tokens, disable_thinking):
    """调一次套餐端点的 chat/completions，成功返回解析后的 JSON，失败抛 ApiError。"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请仔细看这张图片，描述里面有什么内容。"
                            "如果是发票或票据，请逐项列出关键信息"
                            "（如抬头、编号、日期、金额、品目等）。"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }
    if disable_thinking:
        # Coding 端点实测接受 thinking.type=disabled（标准端点会报 1210，两端点校验不一致）
        payload["thinking"] = {"type": "disabled"}

    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": "Bearer " + api_key},
        json=payload,
        timeout=TIMEOUT,
    )
    try:
        body = resp.json()
    except ValueError:
        raise ApiError(resp.status_code, "non-json", resp.text[:200])

    err = body.get("error")
    if err:  # 平台业务错误统一放在 error 字段里
        raise ApiError(resp.status_code, err.get("code", ""), err.get("message", ""))
    if resp.status_code != 200:
        raise ApiError(resp.status_code, "http", "HTTP " + str(resp.status_code))
    if not body.get("choices"):
        raise ApiError(resp.status_code, "parse", "响应里没有 choices：" + str(body)[:200])
    return body


def pick_answer(body):
    """从响应里取 (content, finish_reason)。"""
    choice = body["choices"][0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    return content, choice.get("finish_reason")


def ask(model, data_uri, api_key):
    """单模型问答；若输出被截断（finish_reason=length，思考 token 也计入 max_tokens），
    按 4096 -> 16384 加大预算并关闭思考重试一次；关思考被拒（1210）就只加大预算再试。"""
    body = chat(model, data_uri, api_key, max_tokens=4096, disable_thinking=False)
    content, finish_reason = pick_answer(body)
    if finish_reason == "length":
        print("  [!] finish_reason=length：输出预算被思考 token 吃掉，加大预算并关闭思考重试…")
        try:
            body = chat(model, data_uri, api_key, max_tokens=16384, disable_thinking=True)
        except ApiError as e:
            if e.code != "1210":
                raise
            body = chat(model, data_uri, api_key, max_tokens=16384, disable_thinking=False)
        content, finish_reason = pick_answer(body)
    return body, content, finish_reason


def report_success(model, body, content, finish_reason):
    actual_model = body.get("model", "<响应未回显 model 字段>")
    usage = body.get("usage") or {}

    print("\n==================== 模型回答 ====================")
    answer = strip_think_tags(content)
    print(answer if answer else "（模型返回了空内容）")
    if finish_reason and finish_reason != "stop":
        print(f"[!] 注意：finish_reason={finish_reason}，回答可能被截断")

    print("\n==================== 对账信息 ====================")
    print(f"请求模型          ：{model}")
    print(f"服务端实际使用模型：{actual_model}")
    if actual_model != model:
        print("[!] 两者不一致：服务端静默更换了模型（计费系数与能力可能不同），请以实际模型对账")
    print(
        "token 用量        ：输入 {} / 输出 {} / 合计 {}".format(
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )
    )


def report_failure(failures):
    print("\n==================== 结论 ====================")
    print("已按候选链逐个真试，全部失败：当前这把套餐 Key 走不了直接调视觉模型的这条路。")
    print("每次尝试的原始错误如下（这就是下结论的依据）：")
    for model, e in failures:
        print(f"  - {model}: {e}")
    print(
        """
排查与替代方案：
- 本脚本用的是套餐专属端点 {url}，已排除 1113 的"端点错"成因；
  剩下的失败码指向"能力/模型不在套餐"。
- 官方口径：套餐只保证 glm-5.3 / glm-5.3-flash，视觉理解的官方交付方式是
  套餐附赠的视觉 MCP（npx -y "@z_ai/mcp-server"，Z_AI_API_KEY 填套餐 Key）。
- glm-4.6v / glm-5v-turbo 在套餐端点直调属于无文档背书的实测行为，平台可能已收紧。
- 确需 HTTP 直调视觉模型：用标准 API Key 走 https://open.bigmodel.cn/api/paas/v4。
""".format(url=CHAT_URL)
    )
    sys.exit(1)


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit("请先设置环境变量 " + API_KEY_ENV + "（GLM Coding Plan 套餐 Key）再运行本脚本。")

    data_uri = load_image_data_uri()
    print(f"图片已读取并编码（约 {len(data_uri) // 1024}KB），调用套餐端点识别：{CHAT_URL}\n")

    failures = []
    for i, model in enumerate(CANDIDATE_MODELS, 1):
        print(f"[{i}/{len(CANDIDATE_MODELS)}] 尝试视觉模型：{model}")
        try:
            body, content, finish_reason = ask(model, data_uri, api_key)
        except ApiError as e:
            print(f"  x 失败：{e}")
            failures.append((model, e))
            if e.status == 401:  # 鉴权失败换模型也没用
                sys.exit("Key 无效或未授权（HTTP 401），请检查 " + API_KEY_ENV + "。")
            if e.code not in FALLBACK_ERROR_CODES:
                sys.exit(f"遇到未知错误，终止（不走兜底）：{e}")
            continue
        except requests.RequestException as e:
            sys.exit(f"网络错误（换模型也无济于事）：{e}")

        report_success(model, body, content, finish_reason)
        return

    report_failure(failures)


if __name__ == "__main__":
    main()
