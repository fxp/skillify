#!/usr/bin/env python3
"""用智谱开放平台的【异步】对话接口做批量情感分类。

流程：
  1. POST /paas/v4/async/chat/completions  逐句提交异步任务，拿到任务 id
  2. GET  /paas/v4/async-result/{id}        轮询直到 SUCCESS / FAIL / 超时
  3. 读取 choices[0].message.content 解析出情感标签

审计要求：本任务必须锁定模型 glm-4.6。脚本会同时打印
  - 我请求的模型（REQUESTED_MODEL）
  - 接口实际使用的模型（提交回显的 model + 最终结果回显的 model）
两者不一致时打印醒目告警，并以退出码 1 结束。

注意：技能包 2026-09-07 实测，异步端点会把 glm-4.6 静默替换为 glm-4.7
（同步端点不会），所以下面这个核对不是摆设，实际运行很可能触发告警。

用法：
  export ZHIPUAI_API_KEY=xxx
  python3 main.py
"""

import json
import os
import re
import sys
import time
import uuid

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"
RESULT_URL = f"{BASE_URL}/paas/v4/async-result/{{task_id}}"

# 审计锁定的模型版本，不允许改动
REQUESTED_MODEL = "glm-4.6"

POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 180
HTTP_TIMEOUT_SECONDS = 30

# 三句待分类的句子（分别偏向正面 / 负面 / 中性，便于人工核对结果）
SENTENCES = [
    "这家店的菜品非常好吃，服务也特别贴心，下次还会再来！",
    "快递拖了一个星期才到，包装还破损了，客服处理态度也很敷衍。",
    "今天的会议改到下午三点开始，请准时参加。",
]

SYSTEM_PROMPT = (
    "你是情感分类助手。对用户给出的句子做情感分类，"
    '只输出一个 JSON 对象，格式为 {"sentiment": "positive|negative|neutral"}，'
    "不要输出任何解释或其他文字。"
)


class ApiError(RuntimeError):
    """调用智谱 API 失败（HTTP 非 2xx 或返回 error 结构）。"""


def _check_response(resp: requests.Response) -> dict:
    """统一检查响应：非 2xx 或带 error 结构时抛 ApiError（附平台错误信息）。"""
    try:
        data = resp.json()
    except ValueError:
        raise ApiError(f"HTTP {resp.status_code}，响应不是 JSON: {resp.text[:200]}")
    if not resp.ok:
        err = data.get("error") or {}
        raise ApiError(
            f"HTTP {resp.status_code} code={err.get('code')} message={err.get('message')}"
        )
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise ApiError(f"code={err.get('code')} message={err.get('message')}")
    return data


def submit_async_task(api_key: str, sentence: str) -> dict:
    """提交一个异步对话任务，返回 {'id', 'model', 'request_id', 'task_status'}。"""
    request_id = uuid.uuid4().hex  # 便于审计追溯，平台也回显该字段
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        # 只想要一个分类标签：JSON 输出 + 贪心解码（确定性更强，利于审计复现）。
        # 平台不支持 json_schema，只能 json_object + 在 prompt 里描述结构，
        # 客户端解析时仍需兜底（见 parse_sentiment）。
        "response_format": {"type": "json_object"},
        "do_sample": False,
        "max_tokens": 512,
        "request_id": request_id,
    }
    resp = requests.post(
        SUBMIT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    data = _check_response(resp)
    task_id = data.get("id")
    if not task_id:
        raise ApiError(f"提交异步任务未返回任务 id: {json.dumps(data, ensure_ascii=False)[:200]}")
    return data


def poll_async_result(api_key: str, task_id: str) -> dict:
    """轮询异步结果直到任务完成。

    兼容两种返回形态：官方文档说对话补全结果可能不带 task_status
    （直接出现 choices 即完成），而实测响应又带 task_status，
    所以两个终止条件都判断，避免死等。
    """
    url = RESULT_URL.format(task_id=task_id)
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        result = _check_response(resp)

        status = result.get("task_status")
        if status == "FAIL":
            raise ApiError(f"异步任务 {task_id} 失败: {json.dumps(result, ensure_ascii=False)[:300]}")
        if status == "SUCCESS" or result.get("choices"):
            return result
        # PROCESSING 或其他中间状态：继续等
        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(f"轮询异步任务 {task_id} 超时（{POLL_TIMEOUT_SECONDS}s）")


def parse_sentiment(raw: str) -> str:
    """从模型输出中解析情感标签；json_object 不是强约束，必须做兜底。"""
    text = (raw or "").strip()
    # 兜底 1：模型可能用 ```json ... ``` 代码块包裹
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    # 兜底 2：正文中截取第一个 JSON 对象
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            label = str(obj.get("sentiment", "")).strip().lower()
            if label in ("positive", "negative", "neutral"):
                return label
        except ValueError:
            pass
    # 兜底 3：整体 json.loads
    try:
        obj = json.loads(text)
        label = str(obj.get("sentiment", "")).strip().lower()
        if label in ("positive", "negative", "neutral"):
            return label
    except ValueError:
        pass
    # 全部失败：返回原文片段，明确标出无法解析而不是静默丢错
    return f"<解析失败: {raw[:50]}>"


def normalize_model(name) -> str:
    """模型代码大小写不敏感（平台回显可能是 GLM-4.7 这种大写形式），统一小写再比对。"""
    return (name or "").strip().lower()


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用接口。", file=sys.stderr)
        return 2

    print(f"批量情感分类（异步接口）｜请求模型（锁定版本）: {REQUESTED_MODEL}")
    print(f"共 {len(SENTENCES)} 个句子\n")

    # ---- 第一步：先全部提交，任务在服务端并行跑 ----
    tasks = []
    for idx, sentence in enumerate(SENTENCES, 1):
        submitted = submit_async_task(api_key, sentence)
        tasks.append({"idx": idx, "sentence": sentence, "submit": submitted})
        print(
            f"[{idx}/{len(SENTENCES)}] 已提交 task_id={submitted.get('id')} "
            f"task_status={submitted.get('task_status')} "
            f"提交回显 model={submitted.get('model')}"
        )

    # ---- 第二步：逐个轮询到完成，输出分类结果 ----
    audit_rows = []  # 每个任务的模型核对记录
    for task in tasks:
        idx, submitted = task["idx"], task["submit"]
        result = poll_async_result(api_key, submitted["id"])

        content = ""
        choices = result.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""

        print(f"\n[{idx}/{len(SENTENCES)}] 句子: {task['sentence']}")
        print(f"  task_id={submitted['id']}  情感分类: {parse_sentiment(content)}")

        # ---- 审计核对：请求模型 vs 实际使用模型 ----
        # 以最终结果回显的 model 为准（它才是真正产出内容的模型）；
        # 若最终结果缺失该字段，退回提交时的回显；两者都没有则视为无法核对。
        final_model = result.get("model") or submitted.get("model")
        audit_rows.append(
            {
                "idx": idx,
                "submit_model": submitted.get("model"),
                "final_model": final_model,
            }
        )

    # ---- 审计汇总 ----
    print("\n" + "=" * 60)
    print("审计核对：请求模型 vs 接口实际使用的模型")
    print("=" * 60)
    print(f"请求的模型（锁定版本）: {REQUESTED_MODEL}")
    mismatches = []
    for row in audit_rows:
        actual = row["final_model"]
        if not actual:
            verdict, mismatches = "⛔ 无法确认实际模型（审计失败）", mismatches + [row["idx"]]
            actual_display = "<缺失>"
        elif normalize_model(actual) == REQUESTED_MODEL:
            verdict = "✅ 一致"
            actual_display = actual
        else:
            verdict = "❌ 不一致"
            mismatches.append(row["idx"])
            actual_display = actual
        print(
            f"任务 {row['idx']}: 提交回显 model={row['submit_model']} | "
            f"实际使用 model={actual_display} → {verdict}"
        )

    if mismatches:
        print()
        print("!" * 60)
        print("⛔⛔ 审计告警：检测到模型版本不一致 ⛔⛔")
        print(f"  本任务审计要求锁定模型 {REQUESTED_MODEL}，但以下任务实际"
              f"使用了其他模型: {', '.join(str(i) for i in mismatches)}")
        print("  （智谱异步端点存在静默替换模型的行为，如 glm-4.6 → glm-4.7，")
        print("    本次分类结果不应被采信，请人工复核或改用同步端点重跑。）")
        print("!" * 60)
        return 1

    print("\n✅ 审计通过：所有任务实际使用的模型与请求一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
