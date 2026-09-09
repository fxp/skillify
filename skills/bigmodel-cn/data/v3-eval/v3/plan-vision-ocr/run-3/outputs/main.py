#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

用法：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py

要点（依据 bigmodel-cn 技能包的实测结论）：
- 套餐 Key 必须打 Coding 端点 https://open.bigmodel.cn/api/coding/paas/v4，
  打标准端点 …/api/paas/v4 会报 1113「余额不足」。
- 官方文档口径：套餐只含 glm-5.3 / glm-5.3-flash，视觉走附赠 MCP；
  但实测（2026-09-03）glm-4.6v、glm-5v-turbo 在套餐端点可直接跑图。
  因此本脚本按回退链「先试再下结论」，全部失败才判定套餐用不了视觉。
- 服务端可能静默换模型（如 glm-4.6 → glm-5.3-flash），所以必须打印
  响应里回显的 model 字段对账，不能只信请求参数。
"""

import base64
import os
import re
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_PATH = Path(__file__).resolve().parent / "invoice.png"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 官方限制：单图 ≤5M，≤6000×6000，支持 png

# 回退链：前两个是实测在套餐端点可用的视觉模型，第三个是套餐官方模型、
# 按 models.md 为原生多模态（能直接吃 image_url）。
MODEL_CANDIDATES = ["glm-4.6v", "glm-5v-turbo", "glm-5.3-flash"]

INITIAL_MAX_TOKENS = 8192  # 思考 token 也计入 max_tokens，预算给足
REQUEST_TIMEOUT = 180

THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

PROMPT = (
    "请仔细识别这张发票图片，列出其中的关键内容：发票类型/抬头、"
    "发票号码、开票日期、购买方与销售方信息、金额（含税/税额）、"
    "商品或服务明细等图中实际出现的字段。图中没有的字段不要编造。"
)


def die(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def load_image_data_uri() -> str:
    if not IMAGE_PATH.is_file():
        die(f"找不到图片：{IMAGE_PATH}（请把 invoice.png 放在脚本同目录）")
    size = IMAGE_PATH.stat().st_size
    if size > MAX_IMAGE_BYTES:
        die(f"图片 {size} 字节，超过单图 5M 上限，请压缩后重试")
    b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def strip_think(text: str) -> str:
    """视觉模型的 content 里可能夹 <think>…</think> 思考标签，去掉再展示。"""
    return THINK_TAG_RE.sub("", text).strip()


def describe_http_error(resp: requests.Response) -> str:
    """把 HTTP 错误翻成人话，重点标出业务错误码（如 1113）。"""
    try:
        body = resp.json()
        err = body.get("error") or body
        code = err.get("code", "?")
        message = err.get("message", resp.text[:200])
    except ValueError:
        code, message = "?", resp.text[:200]
    hint = ""
    if str(code) == "1113":
        hint = "（1113 的三种成因：端点错 / 能力不在套餐 / 模型不在套餐；本脚本已用 Coding 端点，即后两者之一）"
    return f"HTTP {resp.status_code} code={code} message={message} {hint}".strip()


def call_model(model: str, data_uri: str, max_tokens: int, disable_thinking: bool):
    """发起一次请求。返回 (HTTP层是否成功, 响应dict或错误描述)。"""
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
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}

    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {os.environ[API_KEY_ENV]}"},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return False, f"网络异常：{exc}"

    if resp.status_code != 200:
        return False, describe_http_error(resp)
    try:
        data = resp.json()
    except ValueError:
        return False, f"响应不是 JSON：{resp.text[:200]}"
    if "choices" not in data:
        return False, f"响应缺少 choices 字段：{str(data)[:200]}"
    return True, data


def try_with_retries(model: str, data_uri: str):
    """对一个模型做「预算被思考吃光 → 翻倍 → 关思考」的补救，返回最好的一次结果。"""
    best = None  # (content, finish_reason, data)
    plan = [
        {"max_tokens": INITIAL_MAX_TOKENS, "disable_thinking": False},
        {"max_tokens": INITIAL_MAX_TOKENS * 2, "disable_thinking": False},
        {"max_tokens": INITIAL_MAX_TOKENS * 2, "disable_thinking": True},
    ]
    for attempt in plan:
        ok, result = call_model(model, data_uri, attempt["max_tokens"], attempt["disable_thinking"])
        if not ok:
            return False, result, None
        choice = result["choices"][0]
        content = strip_think(choice.get("message", {}).get("content") or "")
        finish = choice.get("finish_reason", "")
        if best is None or len(content) > len(best[0]):
            best = (content, finish, result)
        if finish != "length":
            return True, best, None
        # finish_reason == length：正文被截断（思考 token 也计入 max_tokens），继续补救
    return True, best, "length"


def report(model_requested: str, content: str, finish: str, data: dict, truncated: bool) -> None:
    server_model = data.get("model", "<响应未回显 model 字段>")
    print("=== 模型回答 ===")
    print(content if content else "（模型未返回正文内容）")
    print()
    print("=== 对账信息 ===")
    print(f"请求模型       : {model_requested}")
    print(f"服务端实际模型 : {server_model}")
    if server_model != model_requested:
        print(f"[警告] 服务端把你请求的 {model_requested} 换成了 {server_model}，计费与能力按实际模型算")
    usage = data.get("usage")
    if usage:
        print(f"token 用量     : {usage}")
    if truncated or finish == "length":
        print("[警告] finish_reason=length，回答可能被截断，可调大脚本里的 INITIAL_MAX_TOKENS")
    if finish not in ("stop", "length"):
        print(f"[警告] finish_reason={finish}（stop 之外的取值需人工检查）")


def main() -> None:
    if not os.environ.get(API_KEY_ENV):
        die(f"请先设置环境变量 {API_KEY_ENV}（GLM Coding Plan 套餐 Key）")
    data_uri = load_image_data_uri()

    failures = []
    for model in MODEL_CANDIDATES:
        print(f"[尝试] 用套餐端点 + {model} 识别图片……", flush=True)
        ok, result, truncated = try_with_retries(model, data_uri)
        if ok:
            content, finish, data = result
            report(model, content, finish, data, truncated)
            return
        failures.append((model, result))
        print(f"[失败] {model}: {result}", flush=True)

    print()
    print("=== 结论：本次未能用套餐额度完成图片识别 ===")
    for model, reason in failures:
        print(f"  - {model}: {reason}")
    print()
    print("依据说明：")
    print("  1. 本脚本已用套餐专用端点 …/api/coding/paas/v4（排除端点配错），")
    print("     并依次试过 " + "、".join(MODEL_CANDIDATES) + "，均未成功。")
    print("  2. 若上面报 1113：说明视觉模型/图片理解不在你的套餐权益内（官方文档口径")
    print("     套餐只含 glm-5.3 / glm-5.3-flash，视觉理解走附赠的视觉 MCP，而非 chat 接口）。")
    print("  3. 可选出路：用官方视觉 MCP（npx -y \"@z_ai/mcp-server\"，Z_AI_API_KEY 用套餐 Key），")
    print("     或换标准 API Key（环境变量 ZHIPUAI_API_KEY，端点 …/api/paas/v4）调 glm-4.6v 等视觉模型。")
    sys.exit(1)


if __name__ == "__main__":
    main()
