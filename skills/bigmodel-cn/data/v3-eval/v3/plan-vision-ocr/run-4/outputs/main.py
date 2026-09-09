#!/usr/bin/env python3
"""用 GLM Coding Plan（编程套餐）Key 识别同目录下 invoice.png 的内容。

- 只依赖 requests + 标准库，直接 `python3 main.py` 运行。
- 套餐 Key 与标准 API Key 是两套隔离的计费体系：套餐 Key 必须打套餐专用端点
  https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
  （打标准 /api/paas/v4 端点必报 1113“余额不足”，那是端点错了，不是没额度）。
- 套餐官方文档只承诺 glm-5.3 / glm-5.3-flash，但 glm-5.3-flash 本身就是
  视觉模型（chat/completions 支持 image_url 输入）；此外实测 glm-4.6v、
  glm-5v-turbo 也能在套餐端点直接跑图片理解。所以脚本按候选顺序逐个真试，
  全部失败才下“套餐用不了视觉”的结论，并打印每次失败的真实错误码作为依据。
- 对账：打印服务端响应里的 `model` 字段——服务端可能静默更换模型
  （例如 glm-4.6 在套餐端点会被换成 glm-5.3-flash），不一致时给出警告。
- 注意：官方条款把套餐限定在指定工具（Claude Code 等）内使用，自写脚本
  调套餐端点技术上行得通（实测 200），但属于条款之外的用法，生产环境请用标准 Key。
"""

import base64
import mimetypes
import os
import re
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"

# 视觉模型候选，按优先级排列：
#   glm-5.3-flash —— 套餐官方支持的模型，且属于视觉模型（支持 image_url 输入）；
#   glm-4.6v / glm-5v-turbo —— 官方文档未列入套餐，但实测在套餐端点可用。
CANDIDATE_MODELS = ["glm-5.3-flash", "glm-4.6v", "glm-5v-turbo"]

# 思考(thinking)输出也计入 max_tokens，预算太小会把答案截没（finish_reason=length），
# 因此初始给足，被截断时翻倍重试；上限按模型取（glm-4.6v 上限 32768，其余 131072）。
INITIAL_MAX_TOKENS = 8192
MAX_TOKENS_CAP = {"glm-4.6v": 32768}
DEFAULT_MAX_TOKENS_CAP = 131072

PROMPT = (
    "这张图片里有什么内容？如果是发票、票据或单据，请尽量完整地转写关键信息，"
    "包括标题、票据编号、日期、抬头、金额、商品/服务明细等。"
)

# 视觉模型可能把思维链或边界标签混在 content 里，展示前剥掉
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
BOX_RE = re.compile(r"<\|begin_of_box\|>|<\|end_of_box\|>")


class ApiError(Exception):
    """服务端返回的异常，保留 HTTP 状态码和平台错误码供排查。"""

    def __init__(self, status, code, message):
        super().__init__(f"HTTP {status}, code={code}, message={message}")
        self.status = status
        self.code = code
        self.message = message


def load_image_as_data_uri(path: Path) -> str:
    if not path.is_file():
        sys.exit(f"[错误] 找不到图片：{path}（请把 invoice.png 放在脚本同目录下）")
    size = path.stat().st_size
    if size > 5 * 1024 * 1024:
        sys.exit(f"[错误] {path.name} 有 {size} 字节，超过单图 5M 上限，请先压缩")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def chat_once(api_key, model, data_uri, max_tokens):
    """发一次非流式请求，返回解析后的 JSON；服务端报错时抛 ApiError。"""
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
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=(15, 300),
    )
    try:
        body = resp.json()
    except ValueError:
        raise ApiError(resp.status_code, None, f"响应不是 JSON：{resp.text[:300]}")
    err = body.get("error") or {}
    if not resp.ok or err:
        raise ApiError(
            resp.status_code,
            err.get("code") if err else body.get("code"),
            err.get("message") if err else body.get("message") or resp.text[:300],
        )
    if not body.get("choices"):
        raise ApiError(resp.status_code, None, f"响应里没有 choices：{body}")
    return body


def clean_content(content):
    if not content:
        return ""
    return BOX_RE.sub("", THINK_RE.sub("", content)).strip()


def try_model(api_key, model, data_uri):
    """尝试一个模型，必要时翻倍 max_tokens 重试被截断的回答。

    成功返回 (body, content, finish_reason)，失败抛 ApiError。
    """
    cap = MAX_TOKENS_CAP.get(model, DEFAULT_MAX_TOKENS_CAP)
    max_tokens = INITIAL_MAX_TOKENS
    while True:
        body = chat_once(api_key, model, data_uri, max_tokens)
        choice = body["choices"][0]
        finish = choice.get("finish_reason")
        content = clean_content((choice.get("message") or {}).get("content"))
        if finish == "length" and max_tokens < cap:
            # 思考 token 也计入 max_tokens：翻倍预算重试，别把半截结果当成失败
            nxt = min(max_tokens * 2, cap)
            print(f"[提示] {model} 返回 finish_reason=length，"
                  f"把 max_tokens 从 {max_tokens} 提到 {nxt} 重试")
            max_tokens = nxt
            continue
        return body, content, finish


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"[错误] 未设置环境变量 {API_KEY_ENV}（GLM Coding Plan 套餐 Key）")

    data_uri = load_image_as_data_uri(Path(__file__).resolve().parent / "invoice.png")

    failures = []
    for model in CANDIDATE_MODELS:
        print(f"\n===== 尝试模型 {model} =====")
        try:
            body, content, finish = try_model(api_key, model, data_uri)
        except ApiError as e:
            print(f"[失败] {model}: {e}")
            failures.append((model, e))
            continue

        actual = body.get("model")
        print("\n----- 模型的回答 -----")
        print(content or "(模型没有返回文本内容)")
        print("\n----- 对账信息 -----")
        print(f"请求的模型: {model}")
        print(f"服务端实际使用的模型: {actual}")
        if actual and actual != model:
            print(f"[警告] 服务端把模型从 {model} 换成了 {actual}，"
                  "计费和能力都按实际模型算，对账时以服务端返回的为准")
        if finish and finish != "stop":
            print(f"[警告] finish_reason={finish}，结果可能不完整")
        usage = body.get("usage")
        if usage:
            print(f"token 用量: {usage}")
        return

    # 走到这里说明所有候选都试过了，先“真试过”才允许下结论
    print("\n===== 全部候选模型均失败 =====")
    if failures and all(e.code == "1113" for _, e in failures):
        print("结论：这把 GLM Coding Plan 套餐 Key 目前无法用 chat/completions 直接做图片理解。")
        print("依据：脚本用的是套餐专用端点（…/api/coding/paas/v4），已排除“打错端点”这一 1113 成因；")
        print("在此前提下，全部候选视觉模型仍被服务端以 1113（余额不足/无可用资源）拒绝，")
        print("说明“直接调视觉模型”当前不在你的套餐范围内。逐次失败记录如下：")
    else:
        print("暂不能下“套餐不支持视觉”的结论——失败原因并非全是套餐额度/能力问题：")
    for model, e in failures:
        print(f"  - {model}: HTTP {e.status}, code={e.code}, message={e.message}")
    print("可选替代：1) 官方为套餐提供的“视觉理解”本地 MCP（npx -y @z_ai/mcp-server，走套餐额度）；")
    print("          2) 改用标准 API Key（ZHIPUAI_API_KEY）打 https://open.bigmodel.cn/api/paas/v4")
    print("             调 glm-4.6v 等视觉模型。")
    sys.exit(1)


if __name__ == "__main__":
    main()
