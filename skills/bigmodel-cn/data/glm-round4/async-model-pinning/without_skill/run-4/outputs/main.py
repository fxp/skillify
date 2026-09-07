#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量情感分类（智谱异步对话接口版）。

流程：
  1. 用 ZHIPUAI_API_KEY 环境变量中的密钥，向
     POST /api/paas/v4/async/chat/completions 提交 3 个异步分类任务；
  2. 轮询 GET /api/paas/v4/async-result/{id} 直到任务完成；
  3. 打印每条句子的分类结果；
  4. 【审计】逐任务核对「请求的模型」与「接口实际使用的模型」，
     版本锁定为 glm-4.6，任何不一致都会明确报警并以非零码退出。
"""

import os
import sys
import time

import requests

# ---------------------------- 配置 ----------------------------
API_BASE = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = f"{API_BASE}/async/chat/completions"

# 审计要求：本次任务必须锁定 glm-4.6
REQUESTED_MODEL = "glm-4.6"

# 待分类的三句话
SENTENCES = [
    "今天收到了心仪公司的offer，激动得一晚上没睡着！",
    "快递丢了三天，客服电话一直打不通，太让人失望了。",
    "今天下午三点在二楼会议室开项目评审会。",
]

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的句子判断情感倾向，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)

POLL_INTERVAL_SECONDS = 2   # 两次轮询之间的间隔
POLL_TIMEOUT_SECONDS = 300  # 轮询总超时


# ------------------------ 基础工具函数 ------------------------
def build_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def check_response(resp, action):
    """非 200 响应统一抛错，并尽量带出服务端返回的错误信息。"""
    if resp.status_code != 200:
        raise RuntimeError(
            f"{action}失败：HTTP {resp.status_code}，响应内容：{resp.text[:500]}"
        )
    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"{action}失败：响应不是合法 JSON：{resp.text[:500]}")


def submit_task(session, headers, sentence):
    """提交一个异步对话补全任务，返回任务 ID。"""
    payload = {
        "model": REQUESTED_MODEL,  # 审计关键点：请求里显式锁定模型版本
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        "temperature": 0.1,
        "stream": False,
    }
    resp = session.post(SUBMIT_URL, headers=headers, json=payload, timeout=30)
    data = check_response(resp, f"提交任务（句子：{sentence}）")
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError(f"提交任务失败：响应中缺少任务 id：{data}")
    return task_id


def fetch_task_result(session, headers, task_id):
    """查询一次异步任务结果。

    返回值：
      - dict：任务成功，即完整的 ChatCompletionResponse（含实际使用模型）；
      - None：任务仍在 PROCESSING，需要继续轮询；
    任务 FAIL 时直接抛错。
    """
    url = f"{API_BASE}/async-result/{task_id}"
    resp = session.get(url, headers=headers, timeout=30)
    data = check_response(resp, f"查询任务 {task_id} 结果")
    status = data.get("task_status")
    if status == "FAIL":
        raise RuntimeError(f"任务 {task_id} 执行失败（FAIL）：{data}")
    if status == "SUCCESS" or (status is None and "choices" in data):
        return data
    # PROCESSING 或其他中间状态：继续轮询
    return None


def wait_all_tasks(session, headers, tasks):
    """轮询直到所有任务完成或整体超时。

    tasks: {task_id: sentence}，返回 {task_id: 最终响应 dict}。
    某个任务失败/超时不会中断其他任务，错误记录在 errors 中。
    """
    pending = dict(tasks)
    results = {}
    errors = {}
    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while pending and time.time() < deadline:
        for task_id, sentence in list(pending.items()):
            try:
                data = fetch_task_result(session, headers, task_id)
            except RuntimeError as exc:
                errors[task_id] = str(exc)
                del pending[task_id]
                continue
            if data is not None:
                results[task_id] = data
                del pending[task_id]
        if pending:
            time.sleep(POLL_INTERVAL_SECONDS)

    for task_id in pending:  # 整体超时仍未完成的任务
        errors[task_id] = f"轮询超过 {POLL_TIMEOUT_SECONDS} 秒仍未完成"

    return results, errors


# ---------------------------- 审计 ----------------------------
def audit_model_pinning(results):
    """核对每个任务「请求的模型」与「接口实际使用的模型」是否一致。

    返回 True 表示审计通过；发现任何不一致（或拿不到实际模型）都打印
    醒目报警并返回 False。
    """
    print()
    print("=" * 68)
    print(f"模型版本审计（合规核对，要求锁定版本：{REQUESTED_MODEL}）")
    print("=" * 68)

    mismatches = []
    for index, (task_id, data) in enumerate(results.items(), start=1):
        actual_model = (data.get("model") or "").strip()
        # 实际模型缺失同样无法通过审计：不能核对就不能放行
        if not actual_model:
            ok = False
            mismatches.append((index, "（接口未返回实际模型）"))
        else:
            ok = actual_model == REQUESTED_MODEL
            if not ok:
                mismatches.append((index, actual_model))

        mark = "✅ 一致" if ok else "❌ 不一致"
        print(
            f"[{index}/{len(results)}] 请求的模型 = {REQUESTED_MODEL} | "
            f"接口实际使用的模型 = {actual_model or '（缺失）'} | {mark}"
        )

    print("-" * 68)
    if mismatches:
        # 审计红线：请求与实际使用的模型不一致，必须明确报警
        print("🚨🚨🚨 审计报警：模型版本不一致，本次运行不合规！🚨🚨🚨")
        for index, actual_model in mismatches:
            print(
                f"  - 任务 {index}：请求的是 {REQUESTED_MODEL}，"
                f"接口实际使用的是 {actual_model}"
            )
        print(f"审计结论：❌ 未锁定 {REQUESTED_MODEL}，结果不可用于审计用途，请立即核查。")
        return False

    print(f"审计结论：✅ 全部 {len(results)} 个任务实际使用模型均为 {REQUESTED_MODEL}，审计通过。")
    return True


# ---------------------------- 主流程 ----------------------------
def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱 API。", file=sys.stderr)
        sys.exit(2)

    session = requests.Session()
    headers = build_headers(api_key)

    # 1. 批量提交：先把三句话全部提交成异步任务
    print(f"批量提交 {len(SENTENCES)} 个异步分类任务（锁定模型：{REQUESTED_MODEL}）...")
    tasks = {}
    for sentence in SENTENCES:
        task_id = submit_task(session, headers, sentence)
        tasks[task_id] = sentence
        print(f"  已提交：task_id={task_id} | 句子：{sentence}")

    # 2. 轮询等待全部任务完成
    print(f"\n轮询任务结果（间隔 {POLL_INTERVAL_SECONDS}s，超时 {POLL_TIMEOUT_SECONDS}s）...")
    results, errors = wait_all_tasks(session, headers, tasks)

    # 3. 打印分类结果（按提交顺序）
    print()
    print("=" * 68)
    print("情感分类结果")
    print("=" * 68)
    for index, (task_id, sentence) in enumerate(tasks.items(), start=1):
        if task_id in errors:
            print(f"[{index}] 句子：{sentence}\n     ❌ 任务失败：{errors[task_id]}")
            continue
        data = results[task_id]
        content = ""
        choices = data.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
        print(f"[{index}] 句子：{sentence}")
        print(f"     分类：{content.strip() or '（空结果）'}（task_id={task_id}）")

    # 4. 审计核对 + 汇总退出码
    audit_ok = audit_model_pinning(results) if results else False
    if errors:
        print()
        print(f"⚠️ 有 {len(errors)} 个任务失败或超时，详见上方错误信息。")

    if errors or not audit_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
