#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱 GLM 异步对话批量情感分类 + 模型版本审计核对。

流程（全部走智谱异步对话接口，仅依赖 requests + 标准库）：
  1. POST /paas/v4/async/chat/completions  逐条提交 3 个情感分类任务，锁定 model=glm-4.6；
  2. GET  /paas/v4/async-result/{id}        轮询每个任务直到 SUCCESS / FAIL / 超时；
  3. 审计核对：把「请求的 model」与「接口回显的 model」（提交回显 + 结果回显）逐一打印比对，
     任一不一致即打印显著告警，并以退出码 2 结束。

为什么要核对回显 model：异步端点可能静默替换模型（实测 2026-09-07，
请求 glm-4.6 的异步任务实际由 glm-4.7 执行），因此审计场景必须以响应回显的
model 为准，不能相信请求体。比对时做大小写归一化：同一模型的回显大小写
不稳定（实测请求 glm-4.5-air、结果回显 GLM-4.5-Air，属同一模型）。

退出码：0 = 全部任务成功且模型一致；
        1 = 运行错误（缺 API Key / HTTP 或业务错误 / 任务 FAIL / 轮询超时）；
        2 = 任务跑完但检测到模型不一致（审计告警，本批结果不可用于审计留痕）。
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"
RESULT_URL = f"{BASE_URL}/paas/v4/async-result"  # 轮询时拼 /{task_id}

REQUESTED_MODEL = "glm-4.6"  # 审计要求：锁定该模型版本
POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 120
HTTP_TIMEOUT_SECONDS = 30

SENTENCES = [
    "这家店的招牌菜太好吃了，服务也热情，下次还来！",
    "快递拖了一周才到，包装还破了，客服只会打太极。",
    "今天下午三点在会议室开项目复盘会。",
]

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的句子做情感分类，"
    "只输出一个词：正面、负面 或 中性。不要输出任何其他内容。"
)


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def normalize_model(name):
    """大小写归一化后再比对：同一模型的回显大小写不稳定。"""
    return (name or "").strip().lower()


def parse_and_check(resp):
    """解析响应并统一抛错（带出平台 error.code / error.message）。"""
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    error = payload.get("error") if isinstance(payload, dict) else None
    if resp.status_code >= 400 or error:
        detail = f"（平台错误码 {error.get('code')}: {error.get('message')}）" if error else f"（body: {resp.text[:200]}）"
        raise RuntimeError(f"HTTP {resp.status_code}{detail}")
    return payload


def submit_task(sentence, api_key):
    """提交一个异步对话任务，返回任务 id、提交回显 model 与初始状态。"""
    resp = requests.post(
        SUBMIT_URL,
        headers={**auth_headers(api_key), "Content-Type": "application/json"},
        json={
            "model": REQUESTED_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": sentence},
            ],
            # 情感分类是轻量任务，显式关闭思考以降低时延与 token 消耗
            # （glm-4.6 支持 thinking.type 显式开关）
            "thinking": {"type": "disabled"},
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    payload = parse_and_check(resp)
    task_id = payload.get("id")
    if not task_id:
        raise RuntimeError(f"提交异步任务未返回任务 id：{payload}")
    return {"task_id": task_id, "echo_model": payload.get("model"), "task_status": payload.get("task_status")}


def poll_result(task_id, api_key):
    """轮询异步结果直到 SUCCESS / FAIL / 超时，成功时返回完整结果字典。"""
    url = f"{RESULT_URL}/{task_id}"
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        resp = requests.get(url, headers=auth_headers(api_key), timeout=HTTP_TIMEOUT_SECONDS)
        payload = parse_and_check(resp)
        status = payload.get("task_status")
        if status == "SUCCESS":
            return payload
        if status == "FAIL":
            raise RuntimeError(f"异步任务失败（task_id={task_id}）：{payload}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"轮询超时（>{POLL_TIMEOUT_SECONDS}s，task_id={task_id}），最后状态：{status}")
        time.sleep(POLL_INTERVAL_SECONDS)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key），无法调用接口。", file=sys.stderr)
        return 1

    print(f"审计锁定模型：{REQUESTED_MODEL}")
    print(f"批量任务：{len(SENTENCES)} 条情感分类（异步提交 + 轮询结果）\n")

    # 1) 先把全部任务提交出去（异步批处理的意义所在），记录提交回显 model
    tasks = []
    for idx, sentence in enumerate(SENTENCES, 1):
        info = submit_task(sentence, api_key)
        tasks.append({"idx": idx, "sentence": sentence, **info})
        print(
            f"[{idx}/{len(SENTENCES)}] 已提交：task_id={info['task_id']} "
            f"提交回显 model={info['echo_model']} status={info['task_status']}"
        )

    # 2) 逐个轮询拿最终结果；单条失败不中断整个批次，最后统一汇总
    run_error = False
    for task in tasks:
        print(f"\n[{task['idx']}/{len(SENTENCES)}] 轮询结果：{task['sentence']}")
        try:
            final = poll_result(task["task_id"], api_key)
        except Exception as exc:  # 任务 FAIL / 超时 / 网络：记录后继续处理其他任务
            run_error = True
            task["result_model"] = None
            task["label"] = None
            print(f"  获取结果失败：{exc}")
            continue
        task["result_model"] = final.get("model")
        choices = final.get("choices") or [{}]
        task["label"] = (choices[0].get("message") or {}).get("content", "") or ""
        usage = final.get("usage") or {}
        print(f"  分类结果：{task['label'].strip() or '(空)'}")
        print(f"  结果回显 model={task['result_model']}  total_tokens={usage.get('total_tokens')}")

    print("\n=== 分类结果汇总 ===")
    for task in tasks:
        label = task["label"].strip() if task["label"] else "(未取得)"
        print(f"{task['idx']}. {task['sentence']}  ->  {label}")

    # 3) 审计核对：请求的模型 vs 接口实际使用的模型（提交回显 + 结果回显都核对）
    print("\n" + "=" * 66)
    print("审计核对：请求的模型 vs 接口实际使用的模型")
    print("=" * 66)
    mismatch_found = False
    for task in tasks:
        echo = task.get("echo_model")
        actual = task.get("result_model")
        problems = []  # 模型不一致 -> 审计告警（退出码 2）
        notes = []     # 任务未成功等 -> 仅提示（运行错误走退出码 1）
        if echo is not None and normalize_model(echo) != normalize_model(REQUESTED_MODEL):
            problems.append(f"提交回显 model={echo!r} 与请求 {REQUESTED_MODEL!r} 不一致")
        if actual is None:
            notes.append("结果回显缺失（任务未成功，无法确认实际使用的模型）")
        elif normalize_model(actual) != normalize_model(REQUESTED_MODEL):
            problems.append(f"结果回显 model={actual!r} 与请求 {REQUESTED_MODEL!r} 不一致")
        verdict = "不一致" if problems else ("无法核对（任务未成功）" if notes else "一致")
        print(f"[任务{task['idx']}] 请求={REQUESTED_MODEL} | 提交回显={echo} | 结果回显={actual} -> {verdict}")
        for problem in problems:
            mismatch_found = True
            print(f"    *** 审计告警：{problem}")
        for note in notes:
            print(f"    注：{note}")

    if mismatch_found:
        print("\n" + "!" * 66)
        print("!!! 模型版本审计告警：请求的模型与接口实际使用的模型不一致！")
        print(f"!!! 审计要求锁定 {REQUESTED_MODEL}，但平台实际执行了其他模型，")
        print("!!! 本批结果不满足版本锁定要求，请勿用于审计留痕，并联系平台核实。")
        print("!" * 66)
    else:
        print(f"\n审计通过：所有任务实际使用的模型与请求一致（{REQUESTED_MODEL}）。")

    if run_error:
        return 1
    if mismatch_found:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
