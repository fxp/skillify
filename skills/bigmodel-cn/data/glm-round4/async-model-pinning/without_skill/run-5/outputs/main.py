#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱异步对话接口批量情感分类（审计要求：锁定模型 glm-4.6）。

流程：
  1. 从环境变量 ZHIPUAI_API_KEY 读取密钥；
  2. POST /api/paas/v4/async/chat/completions 依次提交 3 个情感分类任务；
  3. GET  /api/paas/v4/async-result/{id} 轮询每个任务，直到 SUCCESS / FAIL；
  4. 审计核对：逐个任务打印「我请求的模型」与「接口实际使用的模型」，
     只要两者不一致（或接口未返回实际模型），输出醒目告警并以非零退出码结束。

依赖：仅 requests（pip install requests）。
运行：ZHIPUAI_API_KEY=你的key python3 main.py
"""

import os
import re
import sys
import time

import requests

# ---------------- 配置 ----------------
API_BASE = "https://open.bigmodel.cn/api"
SUBMIT_URL = API_BASE + "/paas/v4/async/chat/completions"
RESULT_URL = API_BASE + "/paas/v4/async-result/{task_id}"

REQUESTED_MODEL = "glm-4.6"  # 审计要求锁定的模型版本
API_KEY_ENV = "ZHIPUAI_API_KEY"

HTTP_TIMEOUT = 30    # 单次 HTTP 请求超时（秒）
POLL_INTERVAL = 2.0  # 轮询间隔（秒）
POLL_TIMEOUT = 300   # 单个任务的最长轮询时间（秒）

# 三条待分类语句：正面 / 负面 / 中性
SENTENCES = [
    "这家店的菜品非常好吃，服务也很热情，下次一定还来！",
    "快递迟了三天，包装还破损了，客服处理问题的态度特别敷衍。",
    "今天下午三点在二楼会议室开项目复盘会，请大家准时参加。",
]

SYSTEM_PROMPT = (
    "你是一个情感分类器。请对用户给出的句子做情感分类，"
    "只输出下面三个标签中的一个，不要输出任何其他文字：正面、负面、中性"
)


def load_api_key():
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        sys.exit("[错误] 请先设置环境变量 %s，例如：%s=你的key python3 main.py"
                 % (API_KEY_ENV, API_KEY_ENV))
    return key


def check_http(resp, step):
    """统一 HTTP 状态检查，附带响应片段方便排错。"""
    if resp.status_code >= 400:
        raise RuntimeError("%s 失败：HTTP %s，响应：%s"
                           % (step, resp.status_code, resp.text[:500]))


def submit_task(session, headers, index, sentence):
    """提交一个异步情感分类任务，返回任务 id。"""
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
    }
    resp = session.post(SUBMIT_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    check_http(resp, "提交异步任务")
    body = resp.json()
    if isinstance(body.get("error"), dict):
        raise RuntimeError("提交异步任务被拒绝：%s" % body["error"])
    task_id = body.get("id") or body.get("task_id")
    if not task_id:
        raise RuntimeError("提交异步任务成功但没有返回任务 id：%s" % body)
    print("[任务%d] 已提交 task_id=%s task_status=%s"
          % (index, task_id, body.get("task_status")))
    return task_id


def poll_task_once(session, headers, task_id):
    """轮询一次任务状态，返回 (status, result)。status ∈ PROCESSING / SUCCESS / FAIL。"""
    resp = session.get(RESULT_URL.format(task_id=task_id), headers=headers, timeout=HTTP_TIMEOUT)
    check_http(resp, "查询异步结果")
    body = resp.json()
    # 官方文档：对话补全的异步结果直接是顶层的 ChatCompletion 结构；
    # 这里同时兼容结果包在 data 字段里的返回形式。
    result = body.get("data") if isinstance(body.get("data"), dict) else body
    status = result.get("task_status") or body.get("task_status")
    if status is None and ("choices" in result or "model" in result):
        status = "SUCCESS"  # 没带状态字段但带了补全结果，视为成功
    if not status:
        raise RuntimeError("任务 %s 的查询结果结构无法识别：%s" % (task_id, body))
    return status, result


def extract_content(result):
    """从异步结果里取出模型输出的文本。"""
    choices = result.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if isinstance(content, list):  # 多模态 content 数组的兜底处理
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)  # 去掉可能的思考标签
    return content.strip()


def main():
    headers = {
        "Authorization": "Bearer " + load_api_key(),
        "Content-Type": "application/json",
    }
    session = requests.Session()

    print("=" * 68)
    print("审计锁定模型（我请求的模型）: %s" % REQUESTED_MODEL)
    print("异步提交接口: POST %s" % SUBMIT_URL)
    print("结果轮询接口: GET  %s" % RESULT_URL.format(task_id="<task_id>"))
    print("=" * 68)

    # 1) 批量提交 3 个任务
    tasks = []  # (index, sentence, task_id)
    for index, sentence in enumerate(SENTENCES, 1):
        task_id = submit_task(session, headers, index, sentence)
        tasks.append((index, sentence, task_id))

    # 2) 轮询，直到全部完成
    results = {}   # index -> 异步结果 dict
    failures = {}  # index -> 错误说明
    pending = {index: (sentence, task_id) for index, sentence, task_id in tasks}
    deadline = {index: time.monotonic() + POLL_TIMEOUT for index in pending}

    while pending:
        for index, (sentence, task_id) in list(pending.items()):
            try:
                status, result = poll_task_once(session, headers, task_id)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                failures[index] = "查询任务 %s 出错：%s" % (task_id, exc)
                del pending[index]
                continue
            if status == "SUCCESS":
                results[index] = result
                del pending[index]
                print("[任务%d] 轮询完成：SUCCESS" % index)
            elif status in ("FAIL", "FAILED"):
                failures[index] = "任务 %s 处理失败：%s" % (task_id, result)
                del pending[index]
            elif time.monotonic() > deadline[index]:
                failures[index] = ("任务 %s 轮询超时（>%ss），最后状态：%s"
                                   % (task_id, POLL_TIMEOUT, status))
                del pending[index]
        if pending:
            time.sleep(POLL_INTERVAL)

    # 3) 输出分类结果 + 逐任务审计核对
    audit_failures = []
    print()
    print("=" * 68)
    print("批量结果与模型审计核对")
    print("=" * 68)
    for index, sentence, task_id in tasks:
        print()
        print("[任务%d] 句子: %s" % (index, sentence))
        print("[任务%d] task_id: %s" % (index, task_id))
        if index in failures:
            print("[任务%d] 分类结果: 无（任务失败）—— %s" % (index, failures[index]))
            audit_failures.append((index, "任务失败，无法核对实际使用模型"))
            continue
        result = results[index]
        actual_model = result.get("model")
        print("[任务%d] 分类结果: %s" % (index, extract_content(result)))
        print("[任务%d] 我请求的模型      : %s" % (index, REQUESTED_MODEL))
        print("[任务%d] 接口实际使用的模型: %r" % (index, actual_model))
        if actual_model is None:
            print("[任务%d] 模型核对: [告警] 接口未返回实际使用的模型，审计无法确认，按不一致处理" % index)
            audit_failures.append((index, "接口未返回 model 字段，无法核对"))
        elif actual_model != REQUESTED_MODEL:
            print("[任务%d] 模型核对: [告警] 不一致！请求 %r，实际 %r"
                  % (index, REQUESTED_MODEL, actual_model))
            audit_failures.append((index, "请求 %r，实际 %r" % (REQUESTED_MODEL, actual_model)))
        else:
            print("[任务%d] 模型核对: [通过] 与请求一致" % index)

    # 4) 汇总
    print()
    print("=" * 68)
    if audit_failures:
        print("!!!!!! 审计告警：存在模型版本不一致（或无法核对）的任务 !!!!!!")
        for index, reason in audit_failures:
            print("  - 任务%d: %s" % (index, reason))
        print("!!!!!! 审计要求：模型必须锁定为 %s，请立即排查 !!!!!!" % REQUESTED_MODEL)
        sys.exit(1)
    print("全部 %d 个任务完成，实际使用模型与请求模型全部一致（%s），审计通过。"
          % (len(tasks), REQUESTED_MODEL))
    print("=" * 68)


if __name__ == "__main__":
    main()
