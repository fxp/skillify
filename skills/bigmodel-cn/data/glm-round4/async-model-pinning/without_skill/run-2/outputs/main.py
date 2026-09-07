#!/usr/bin/env python3
"""智谱异步对话接口批量情感分类（带模型版本审计）。

流程：
  1. POST /api/paas/v4/async/chat/completions 批量提交 3 个情感分类任务；
  2. GET  /api/paas/v4/async-result/{task_id} 轮询，直到 SUCCESS / FAIL；
  3. 审计核对：请求的模型（锁定 glm-4.6）与接口在 SUCCESS 结果里返回的
     model 字段（接口实际使用的模型）必须逐任务一致；不一致则打印醒目
     报警，并以退出码 2 结束（与普通错误 1 区分，便于审计/CI 捕获）。

API Key 从环境变量 ZHIPUAI_API_KEY 读取，仅依赖 requests，
可直接 `python3 main.py` 运行。
"""

import json
import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = f"{BASE_URL}/async/chat/completions"
RESULT_URL_TMPL = f"{BASE_URL}/async-result/{{task_id}}"

# 审计要求：模型版本必须锁定为 glm-4.6，不得被服务端改写为其他版本。
PINNED_MODEL = "glm-4.6"

SENTENCES = [
    "这家店的服务特别热情，菜也好吃，下次还来！",
    "快递拖了一周才到，包装还破了，客服处理得很敷衍，太失望了。",
    "明天的例会改到下午三点，请准时参加。",
]

SYSTEM_PROMPT = (
    "你是一个情感分类器。对用户给出的句子判断情感倾向，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)

HTTP_TIMEOUT_SEC = 30
POLL_INTERVAL_SEC = 2.0
POLL_TIMEOUT_SEC = 300  # 单个任务的轮询上限

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MODEL_MISMATCH = 2  # 专供审计识别：模型版本不一致


def check_http(resp: requests.Response, what: str) -> None:
    """非 2xx 响应统一抛错，并把响应体带进错误信息，方便定位。"""
    if not resp.ok:
        raise RuntimeError(
            f"{what} 失败：HTTP {resp.status_code}，响应：{resp.text[:500]}"
        )


def submit_task(headers: dict, sentence: str) -> str:
    """提交一个异步分类任务，返回任务 id。"""
    payload = {
        "model": PINNED_MODEL,  # 审计：每次请求都显式锁定模型版本
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        "thinking": {"type": "disabled"},  # 分类任务不需要思维链，输出更干净
    }
    resp = requests.post(SUBMIT_URL, headers=headers, json=payload, timeout=HTTP_TIMEOUT_SEC)
    check_http(resp, f"提交句子「{sentence}」的异步任务")
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError(f"提交接口未返回任务 id，响应：{json.dumps(data, ensure_ascii=False)}")
    return task_id


def wait_for_task(headers: dict, task_id: str) -> dict:
    """轮询任务直到 SUCCESS / FAIL / 超时，返回 SUCCESS 时的完整结果。

    接口实际使用的模型以这里返回的 model 字段为准
    （提交接口回显的 model 只是请求回声，不作为审计依据）。
    """
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while True:
        resp = requests.get(
            RESULT_URL_TMPL.format(task_id=task_id),
            headers=headers,
            timeout=HTTP_TIMEOUT_SEC,
        )
        check_http(resp, f"查询任务 {task_id}")
        data = resp.json()
        status = data.get("task_status")
        if status == "SUCCESS":
            return data
        if status == "FAIL":
            raise RuntimeError(
                f"任务 {task_id} 处理失败（FAIL），响应：{json.dumps(data, ensure_ascii=False)}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(f"任务 {task_id} 轮询超过 {POLL_TIMEOUT_SEC}s，状态仍为 {status}")
        time.sleep(POLL_INTERVAL_SEC)


def extract_label(result: dict) -> str:
    """从 SUCCESS 结果里取出分类文本。"""
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(
            f"任务成功但未返回 choices，完整响应：{json.dumps(result, ensure_ascii=False)[:500]}"
        )
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    # 折叠换行和多余空白，避免标签被模型输出的排版干扰
    return " ".join(content.split())


def audit_model_pinning(tasks: list) -> int:
    """逐任务核对「请求的模型」与「接口实际使用的模型」，返回不一致的任务数。"""
    print("=" * 64)
    print(f"[审计] 模型版本核对（审计要求：锁定 {PINNED_MODEL}）")
    mismatch_count = 0
    for task in tasks:
        result = task.get("result") or {}
        actual = result.get("model")
        actual_display = actual if actual else "（接口未返回 model 字段）"
        matched = actual == PINNED_MODEL
        print(
            f"  [{task['idx']}/{len(tasks)}] 任务 {task['task_id']}"
            f" | 我请求的模型: {PINNED_MODEL}"
            f" | 接口实际使用的模型: {actual_display}"
            f" | {'一致' if matched else '不一致'}"
        )
        if not matched:
            mismatch_count += 1
    return mismatch_count


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        return EXIT_ERROR
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"智谱异步批量情感分类 | 审计锁定模型: {PINNED_MODEL}")
    print("=" * 64)

    # 1) 批量提交：先把 3 个任务全部提交上去，再统一轮询取回
    tasks = []
    for idx, sentence in enumerate(SENTENCES, 1):
        task_id = submit_task(headers, sentence)
        tasks.append({"idx": idx, "sentence": sentence, "task_id": task_id})
        print(f"[{idx}/{len(SENTENCES)}] 已提交 | 任务ID: {task_id} | 句子: {sentence}")

    # 2) 轮询取回结果并输出分类
    print("-" * 64)
    for task in tasks:
        task["result"] = wait_for_task(headers, task["task_id"])
        print(f"[{task['idx']}/{len(SENTENCES)}] 分类完成 | 任务ID: {task['task_id']}")
        print(f"    句子: {task['sentence']}")
        print(f"    分类: {extract_label(task['result'])}")

    # 3) 审计核对模型版本
    mismatch_count = audit_model_pinning(tasks)
    if mismatch_count == 0:
        print(f"[审计] 核对通过：{len(tasks)}/{len(tasks)} 个任务实际使用的模型均为 {PINNED_MODEL}。")
        return EXIT_OK

    print("!" * 64)
    print("!! 审计报警：检测到模型版本不一致，本次全部结果不可信！")
    for task in tasks:
        result = task.get("result") or {}
        actual = result.get("model")
        if actual != PINNED_MODEL:
            print(
                f"!!   任务 {task['task_id']}"
                f"（句子「{task['sentence']}」）:"
                f" 请求={PINNED_MODEL} / 实际={actual if actual else '（未返回）'}"
            )
    print(f"!! 共 {mismatch_count}/{len(tasks)} 个任务不一致；"
          f"审计要求锁定 {PINNED_MODEL}，请立即排查后重跑。")
    print("!" * 64)
    return EXIT_MODEL_MISMATCH


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.RequestException as exc:
        print(f"错误：网络请求失败：{exc}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    except (RuntimeError, TimeoutError, ValueError) as exc:
        # ValueError：接口返回了非 JSON 内容时 resp.json() 会抛出
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
