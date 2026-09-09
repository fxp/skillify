#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GLM Coding Plan（编程套餐）额度识别同目录下 invoice.png 的内容。

用法：
    export GLM_CODING_PLAN_API_KEY=你的套餐Key
    python3 main.py

为什么这样写（依据 docs.bigmodel.cn 与实测记录，2026-09）：
- 套餐 Key 与标准 API Key 是两套隔离计费体系：套餐 Key 必须打 Coding 端点
  https://open.bigmodel.cn/api/coding/paas/v4/*；打标准端点 …/api/paas/v4 必报 1113 余额不足。
- 官方文档：所有套餐档位都包含 glm-5.3 / glm-5.3-flash；其中 glm-5.3-flash 是原生多模态模型，
  chat/completions 的 content 数组里传 image_url（支持 base64 Data URL）即可识别图片。
- 实测：Coding 端点接受 thinking:{"type":"disabled"}（标准端点反而报 1210）。关思考省套餐额度，
  也避免思考 token 计入 max_tokens 把正文预算吃光。
- 对账：Coding 端点可能静默换模型（如 glm-4.6 → glm-5.3-flash），所以必须读回响应里的 model 字段。

依赖：仅 requests。
"""

import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

API_KEY_ENV = "GLM_CODING_PLAN_API_KEY"
CHAT_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
IMAGE_PATH = Path(__file__).resolve().parent / "invoice.png"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 官方限制：单图 ≤5MB、≤6000×6000、jpg/png/jpeg
TIMEOUT_SECONDS = 180

PROMPT = (
    "这是一张发票图片。请仔细识别图中内容，逐项列出你能辨认的关键信息，"
    "包括：发票名称/类型、发票号码、开票日期、购买方、销售方、"
    "金额（不含税/税额/价税合计）及其他字段。看不清的请注明“无法辨认”。"
)

# 依序真实尝试，前一个失败才试下一个：
# 1) glm-5.3-flash + 关闭思考：官方明说所有套餐档位含 glm-5.3-flash，且它是原生多模态模型，
#    可直接吃 image_url——这是套餐内视觉能力的首选路径；
# 2) glm-5.3-flash 不带 thinking：若 thinking 参数被服务端拒绝（如 1210），排除参数干扰再试一次；
# 3) glm-4.6v、4) glm-5v-turbo：专职视觉模型，实测（2026-09-03）套餐 Key 在 Coding 端点可用，
#    但官方文档未背书，仅作兜底。
ATTEMPTS = [
    ("glm-5.3-flash", {"thinking": {"type": "disabled"}}),
    ("glm-5.3-flash", {}),
    ("glm-4.6v", {}),
    ("glm-5v-turbo", {}),
]


class AttemptFailure(Exception):
    """单次尝试失败，携带给人看的证据（HTTP 状态 + 服务端原始报错）。"""


def fail(message: str) -> "None":
    print(f"[错误] {message}", file=sys.stderr)
    sys.exit(1)


def load_image_as_data_uri() -> str:
    if not IMAGE_PATH.is_file():
        fail(f"找不到图片：{IMAGE_PATH}（请把 invoice.png 放到和 main.py 同一个目录）")
    raw = IMAGE_PATH.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        print(
            f"[警告] 图片 {len(raw) / 1024 / 1024:.1f}MB 超过官方单图 5MB 限制，"
            "可能被服务端拒绝，仍会尝试。"
        )
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def call_model(model: str, extra_params: dict, data_uri: str, api_key: str) -> dict:
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
        "max_tokens": 4096,
        "stream": False,
    }
    payload.update(extra_params)

    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise AttemptFailure(f"网络异常：{exc!r}") from exc

    try:
        data = resp.json()
    except ValueError:
        raise AttemptFailure(f"HTTP {resp.status_code}，响应不是 JSON：{resp.text[:300]}")

    error = data.get("error")
    if resp.status_code != 200 or error:
        # 1113（余额不足或无可用资源包）在套餐体系下有三种成因：
        # 端点打错 / 能力不在套餐 / 模型不在套餐。本脚本端点已固定为 Coding 端点，
        # 所以出现 1113 通常意味着“模型或该能力当前不在套餐额度内”。
        code = (error or {}).get("code", "")
        hint = "（1113 在套餐体系下通常表示该模型/能力不在套餐内，或额度已耗尽）" if str(code) == "1113" else ""
        message = (error or {}).get("message", resp.text[:200])
        raise AttemptFailure(f"HTTP {resp.status_code} code={code} {message}{hint}")

    choice = (data.get("choices") or [{}])[0]
    answer = (choice.get("message") or {}).get("content")
    if not isinstance(answer, str):
        answer = "" if answer is None else json.dumps(answer, ensure_ascii=False)
    # 部分视觉模型会在 content 里夹 <think>…</think> 思考标签，剥掉再展示
    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()

    return {
        "served_model": data.get("model", ""),
        "content": answer,
        "finish_reason": choice.get("finish_reason", ""),
        "usage": data.get("usage", {}),
    }


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        fail(f"请先设置环境变量 {API_KEY_ENV} 为你的 GLM Coding Plan 套餐 Key")

    data_uri = load_image_as_data_uri()

    failures = []
    for model, extra_params in ATTEMPTS:
        label = model + ("（关闭思考）" if extra_params else "")
        print(f"\n===== 尝试 {label} =====")
        try:
            result = call_model(model, extra_params, data_uri, api_key)
        except AttemptFailure as exc:
            print(f"[失败] {exc}")
            failures.append(f"{label}: {exc}")
            continue

        if not result["content"]:
            # 200 但正文为空：多半是 max_tokens 被思考 token 吃光（finish_reason=length）
            print(
                f"[异常] 返回 200 但正文为空，finish_reason={result['finish_reason']!r}，"
                "换下一个尝试。"
            )
            failures.append(f"{label}: 200 但空正文（finish_reason={result['finish_reason']}）")
            continue

        print("\n----- 模型的回答 -----")
        print(result["content"])
        print("\n----- 对账信息 -----")
        print(f"请求模型     : {model}")
        served = result["served_model"] or "（响应里没有 model 字段）"
        print(f"服务端实际模型: {served}")
        if served != model:
            print("注意：实际模型与请求的不同（Coding 端点存在静默重路由），对账请以上面这行为准。")
        print(f"finish_reason: {result['finish_reason']}")
        print(f"token 用量   : {json.dumps(result['usage'], ensure_ascii=False)}")
        return

    print("\n==================== 结论 ====================")
    print("已依次真实尝试以下组合，全部失败（证据即上面的服务端原始报错）：")
    for item in failures:
        print(f"  - {item}")
    print(
        "\n依据这些报错判断：\n"
        "  * 若多为 1113：直接的图像输入当前不在套餐额度内。官方把套餐的图像理解能力主要放在\n"
        "    附赠的视觉理解 MCP 里（npx -y \"@z_ai/mcp-server\"，Z_AI_API_KEY 用套餐 Key），\n"
        "    而不是 chat/completions 直传图片；也可能是本时段套餐额度已耗尽（每 5 小时滚动重置）。\n"
        "  * 若为 1210/1214 等：参数或模型名问题，请把上面的报文原样反馈排查。\n"
        "  * 另注意官方条款：套餐仅限在指定工具与产品环境中使用，自写脚本调用能否消耗套餐额度以官方为准。\n"
        "在排除以上原因前，不能断言“套餐用不了视觉”——请先核对报错码与套餐额度再下结论。"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
