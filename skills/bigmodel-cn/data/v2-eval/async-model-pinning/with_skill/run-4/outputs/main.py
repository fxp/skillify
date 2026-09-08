#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱 AI 异步对话接口批量情感分类（含模型版本审计）。

流程（异步接口 = 提交任务 + 轮询结果）：
  1. POST /paas/v4/async/chat/completions   逐句提交，立即拿任务 id
  2. GET  /paas/v4/async-result/{id}        轮询到 SUCCESS / FAIL
  3. 审计核对：请求的模型 vs 响应回显的模型（提交回显 + 最终结果回显）

⚠️ 审计背景（平台实测行为，不是文档写的）：
  智谱的【异步】端点可能静默替换模型——请求 glm-4.6，实际由 glm-4.7 服务，
  接口不报错、HTTP 200，同步端点则不会。所以绝不能信任请求体里写了什么，
  必须读回响应里的 model 字段做核对；任何不一致都要明确报警，
  并以非零退出码结束，供审计流水留痕。

用法：
  export ZHIPUAI_API_KEY=你的Key
  python3 main.py
"""

import os
import sys
import time

import requests

# ---------------- 配置 ----------------
BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"

REQUESTED_MODEL = "glm-4.6"  # 审计要求锁定的模型版本

SENTENCES = [
    "这家店的服务太贴心了，东西也好吃，下次还会再来。",
    "快递拖了整整一个星期，包装还破了，太让人失望了。",
    "明天上午十点在会议室开项目评审会。",
]
VALID_LABELS = ("积极", "消极", "中性")

POLL_INTERVAL_S = 2   # 轮询间隔（秒）
POLL_TIMEOUT_S = 180  # 单个任务轮询总超时（秒）
HTTP_TIMEOUT_S = 30   # 单次 HTTP 请求超时（秒）


def auth_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _check_http(resp: requests.Response, action: str) -> None:
    """带上下文地抛 HTTP 错误，报错信息里带上响应体，方便排查。"""
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{action}失败：HTTP {resp.status_code}，响应体：{resp.text[:500]}"
        )


def submit_task(sentence: str, api_key: str):
    """提交一个异步分类任务。

    返回 (task_id, 提交响应回显的 model)。注意：异步接口不支持 stream 参数，
    请求体里不能带，带了会报参数错误。
    """
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是情感分类器。对用户给出的句子做情感分类，"
                    "只输出以下三个标签之一，不要输出任何解释或其他文字："
                    "积极 / 消极 / 中性"
                ),
            },
            {"role": "user", "content": f"句子：{sentence}"},
        ],
    }
    resp = requests.post(
        SUBMIT_URL,
        headers=auth_headers(api_key),
        json=payload,
        timeout=HTTP_TIMEOUT_S,
    )
    _check_http(resp, "提交异步任务")
    body = resp.json()
    task_id = body.get("id")
    if not task_id:
        raise RuntimeError(f"提交响应里没有任务 id，无法轮询：{body}")
    return task_id, body.get("model")


def poll_result(task_id: str, api_key: str) -> dict:
    """轮询异步结果，SUCCESS 时返回完整结果 dict；FAIL / 超时抛异常。

    处理中（PROCESSING）的响应只有 model / task_status / request_id 等
    壳字段，没有 choices，必须轮询到 SUCCESS 再取内容。
    """
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    waited = 0
    while True:
        resp = requests.get(
            url, headers=auth_headers(api_key), timeout=HTTP_TIMEOUT_S
        )
        _check_http(resp, "查询异步结果")
        body = resp.json()
        status = body.get("task_status")
        if status == "SUCCESS":
            return body
        if status == "FAIL":
            raise RuntimeError(f"异步任务失败（task_status=FAIL）：{body}")
        if waited >= POLL_TIMEOUT_S:
            raise TimeoutError(
                f"轮询超时（>{POLL_TIMEOUT_S}s）：任务 {task_id} 仍处于 {status}"
            )
        time.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S


def norm_model(name) -> str:
    """平台回显的模型名大小写不固定（实测 glm-4.5-air 会回显成 GLM-4.5-Air，
    仍是同一个模型），所以判定“是否同一模型”时统一小写比较；
    打印审计记录时保留原始字符串，不做改写。"""
    return (name or "").strip().lower()


def audit_task(row: dict):
    """审计单个任务：请求模型 vs 接口实际使用的模型。

    判定规则（从严，审计上不能含糊）：
      - “实际使用的模型”以最终轮询结果回显的 model 字段为准；
      - 提交响应回显的 model 一并核对，任何一处与请求不一致都算不一致；
      - 结果回显缺失 model 视为“无法核实”，同样报警；
      - 仅大小写差异不算换模型（见 norm_model）。
    返回 (hard_problems, soft_warnings)。
    """
    hard, soft = [], []
    actual = row.get("actual_model")
    submit_echo = row.get("submit_model")

    if actual is None:
        hard.append("最终结果回显缺少 model 字段，无法核实实际使用的模型")
    elif norm_model(actual) != norm_model(REQUESTED_MODEL):
        hard.append(
            f"接口实际使用的模型为 {actual!r}，与请求的 {REQUESTED_MODEL!r} 不一致"
        )

    if submit_echo is None:
        soft.append("提交响应未回显 model 字段（留档提示）")
    elif norm_model(submit_echo) != norm_model(REQUESTED_MODEL):
        hard.append(
            f"提交响应回显的模型为 {submit_echo!r}，与请求的 {REQUESTED_MODEL!r} 不一致"
        )
    return hard, soft


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print(
            "错误：未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key），"
            "请先 export ZHIPUAI_API_KEY=...",
            file=sys.stderr,
        )
        return 2

    print(f"本次批量任务：{len(SENTENCES)} 个句子的情感分类（异步接口）")
    print(f"审计锁定模型（我请求的模型）：{REQUESTED_MODEL}")
    print("-" * 64)

    # ---- 阶段 1：批量提交，先拿全任务 id ----
    tasks = []
    for i, sentence in enumerate(SENTENCES, 1):
        task_id, submit_model = submit_task(sentence, api_key)
        tasks.append(
            {
                "idx": i,
                "sentence": sentence,
                "task_id": task_id,
                "submit_model": submit_model,
            }
        )
        print(f"[提交] 任务{i}：id={task_id}，提交回显 model={submit_model!r}")

    # ---- 阶段 2：逐个轮询到终态 ----
    print("-" * 64)
    for t in tasks:
        result = poll_result(t["task_id"], api_key)
        t["actual_model"] = result.get("model")  # 实际使用的模型（以此为准）
        t["request_id"] = result.get("request_id")
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        content = content.strip() if isinstance(content, str) else ""
        t["finish_reason"] = choice.get("finish_reason")
        t["label"] = content if content in VALID_LABELS else None
        t["raw_content"] = content

    # ---- 阶段 3：输出分类结果 + 模型版本审计 ----
    all_hard, all_soft = [], []
    for t in tasks:
        hard, soft = audit_task(t)
        all_hard.extend(f"任务{t['idx']}：{p}" for p in hard)
        all_soft.extend(f"任务{t['idx']}：{w}" for w in soft)

        print(f"\n【任务 {t['idx']}】")
        print(f"  句子                ：{t['sentence']}")
        if t["label"]:
            print(f"  情感分类结果        ：{t['label']}")
        else:
            print(f"  情感分类结果        ：无法解析（原始输出：{t['raw_content']!r}）")
        print(f"  finish_reason       ：{t['finish_reason']}")
        print(f"  task_id / request_id：{t['task_id']} / {t.get('request_id')}")
        print(f"  我请求的模型        ：{REQUESTED_MODEL}")
        print(f"  接口实际使用的模型  ：{t.get('actual_model')!r}（最终结果回显）")
        print(f"  提交响应回显的模型  ：{t['submit_model']!r}")
        if hard:
            print("  ⚠ 该任务模型核对不通过，详见下方审计结论")

    print("\n" + "=" * 64)
    print("模型版本审计结论")
    print("=" * 64)
    for w in all_soft:
        print(f"  [提示] {w}")
    if all_hard:
        for p in all_hard:
            print(f"  [不一致] {p}")
        print()
        print("!" * 64, file=sys.stderr)
        print(
            f"【审计报警】检测到 {len(all_hard)} 处模型与请求的 {REQUESTED_MODEL} 不一致！",
            file=sys.stderr,
        )
        print(
            "异步端点存在静默换模型行为（如 glm-4.6 被替换为 glm-4.7），",
            file=sys.stderr,
        )
        print(
            "本次结果不满足“锁定 glm-4.6”的审计要求，请勿直接采信，",
            file=sys.stderr,
        )
        print("退出码置为 1。请与平台确认路由策略后再决定是否放行。", file=sys.stderr)
        print("!" * 64, file=sys.stderr)
        return 1

    print(f"  审计通过：{len(tasks)} 个任务的实际模型均为 {REQUESTED_MODEL}（忽略大小写）。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, TimeoutError, requests.RequestException) as exc:
        print(f"\n执行失败：{exc}", file=sys.stderr)
        sys.exit(1)
