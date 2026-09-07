#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱异步对话接口批量情感分类（模型版本锁定 / 审计核对版）。

流程：
  1. 读取环境变量 ZHIPUAI_API_KEY；
  2. 依次提交 3 个异步情感分类任务（POST /api/paas/v4/async/chat/completions）；
  3. 逐个轮询任务结果（GET /api/paas/v4/async-result/{id}）直到完成；
  4. 【审计】打印「我请求的模型」与「接口实际使用的模型」并逐条核对，
     任何一条不一致都给出醒目告警，并以退出码 1 结束。

依赖：仅 requests。运行：python3 main.py
"""

import os
import sys
import time
import uuid

import requests

# ============================ 配置 ============================

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = BASE_URL + "/async/chat/completions"
RESULT_URL_TEMPLATE = BASE_URL + "/async-result/{task_id}"  # 任务 id 拼在路径上

# 审计要求：模型版本锁定为 glm-4.6，不得改动。
REQUESTED_MODEL = "glm-4.6"

POLL_INTERVAL_SECONDS = 2     # 轮询间隔
POLL_TIMEOUT_SECONDS = 300    # 单个任务轮询超时
HTTP_TIMEOUT_SECONDS = 30     # 单次 HTTP 请求超时

# 待分类的三句话
SENTENCES = [
    "这家店的菜品非常好吃，服务也特别贴心，下次一定还来！",
    "快递迟了三天，包装还破了，找客服处理态度还很差。",
    "今天下午三点在二楼会议室开项目复盘会，请准时参加。",
]

SYSTEM_PROMPT = (
    "你是一个情感分类器。对用户给出的句子判断情感倾向，"
    "只输出一个词作为标签：正面、负面 或 中性。不要输出任何其他内容。"
)


# ======================= 基础工具函数 =========================

def require_api_key():
    """从环境变量读取 API Key，缺失则直接报错退出。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用接口。", file=sys.stderr)
        sys.exit(2)
    return api_key


def auth_headers(api_key):
    return {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }


# ===================== 异步接口：提交 + 轮询 ====================

def submit_async_task(sentence, index, api_key):
    """提交一个异步对话补全任务，返回提交回执 {model, id, request_id, task_status}。"""
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        # 分类任务要稳定输出，关闭思考、低温采样
        "thinking": {"type": "disabled"},
        "temperature": 0.1,
        "max_tokens": 512,
        # 自带 request_id（6-64 字符），便于审计追溯
        "request_id": "sent-cls-{}-{}".format(index, uuid.uuid4().hex[:8]),
    }
    resp = requests.post(
        SUBMIT_URL, json=payload, headers=auth_headers(api_key),
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "提交异步任务失败: HTTP {} body={}".format(resp.status_code, resp.text)
        )
    receipt = resp.json()
    task_id = receipt.get("id")
    if not task_id:
        raise RuntimeError("提交回执中没有任务 id，无法轮询: {}".format(receipt))
    return receipt


def poll_async_result(task_id, api_key):
    """轮询查询异步结果，任务完成后返回 ChatCompletionResponse（含实际 model 与 choices）。"""
    url = RESULT_URL_TEMPLATE.format(task_id=task_id)
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        resp = requests.get(
            url, headers=auth_headers(api_key), timeout=HTTP_TIMEOUT_SECONDS
        )
        if resp.status_code != 200:
            raise RuntimeError(
                "查询异步结果失败: HTTP {} body={}".format(resp.status_code, resp.text)
            )
        data = resp.json()
        status = data.get("task_status")

        if status == "PROCESSING":
            if time.time() > deadline:
                raise TimeoutError(
                    "任务 {} 轮询超过 {} 秒仍未完成".format(task_id, POLL_TIMEOUT_SECONDS)
                )
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # 完成的对话任务返回 ChatCompletionResponse：
        # 带 task_status=SUCCESS，或不带 task_status 但包含 choices。
        if status == "SUCCESS" or "choices" in data:
            return data

        if status == "FAIL":
            raise RuntimeError("任务 {} 处理失败(FAIL): {}".format(task_id, data))
        raise RuntimeError("任务 {} 返回了无法识别的响应: {}".format(task_id, data))


def extract_answer(result):
    """从完成的任务结果中取出模型输出的分类标签。"""
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("任务结果中缺少 choices[0].message.content: {}".format(result)) from exc
    return content.strip()


# ========================== 审计核对 ===========================

def audit_alarm(index, requested, actual):
    """模型版本不一致时的醒目告警（审计要求：不能含糊）。"""
    print()
    print("=" * 68)
    print("!!!  审计告警：模型版本不一致  !!!")
    print("    任务编号      : {}".format(index))
    print("    我请求的模型  : {}".format(requested))
    print("    接口实际使用  : {}".format(actual if actual else "<结果中未返回 model 字段>"))
    print("    审计结论      : 不一致 —— 本批次结果不可用于审计，请立即排查！")
    print("=" * 68)
    print()


def audit_report(records):
    """打印审计核对汇总。存在任何不一致返回 False。"""
    print()
    print("==================== 审计核对汇总 ====================")
    print("本批次锁定的请求模型: {}".format(REQUESTED_MODEL))
    all_match = True
    for record in records:
        ok = record["actual_model"] == REQUESTED_MODEL
        all_match = all_match and ok
        print(
            "任务 {index}（{sentence}）\n"
            "    我请求的模型 : {requested}\n"
            "    接口实际使用 : {actual}\n"
            "    核对结果     : {verdict}".format(
                index=record["index"],
                sentence=record["sentence"],
                requested=REQUESTED_MODEL,
                actual=record["actual_model"] if record["actual_model"]
                else "<结果中未返回 model 字段>",
                verdict="一致" if ok else "不一致（告警）",
            )
        )
    print("======================================================")
    if all_match:
        print("审计结论: 全部任务模型一致，符合版本锁定要求。")
    else:
        print("审计结论: !!! 存在模型版本不一致，本批次结果不可用于审计 !!!")
    return all_match


# ============================ 主流程 ============================

def main():
    api_key = require_api_key()
    print("使用异步接口 {} 批量提交 {} 个情感分类任务（锁定模型 {}）".format(
        SUBMIT_URL, len(SENTENCES), REQUESTED_MODEL))

    # 第一步：先把所有任务提交出去（异步提交，拿任务 id）
    tasks = []
    for index, sentence in enumerate(SENTENCES, start=1):
        receipt = submit_async_task(sentence, index, api_key)
        print(
            "[提交] 任务 {}/{} 已受理: task_id={} task_status={} 提交回执model={}".format(
                index, len(SENTENCES),
                receipt.get("id"), receipt.get("task_status"), receipt.get("model"),
            )
        )
        tasks.append({"index": index, "sentence": sentence, "task_id": receipt.get("id")})

    # 第二步：逐个轮询拿结果
    records = []
    for task in tasks:
        result = poll_async_result(task["task_id"], api_key)
        label = extract_answer(result)
        actual_model = result.get("model")  # 实际使用的模型，审计核对依据
        print("[结果] 任务 {}: 情感标签 = {}".format(task["index"], label))
        record = {
            "index": task["index"],
            "sentence": task["sentence"],
            "actual_model": actual_model,
            "label": label,
        }
        records.append(record)
        # 不一致立即就地告警，最后汇总再统一判定
        if actual_model != REQUESTED_MODEL:
            audit_alarm(task["index"], REQUESTED_MODEL, actual_model)

    # 第三步：输出分类结果与审计汇总
    print()
    print("==================== 情感分类结果 ====================")
    for record in records:
        print("{}. [{}] {}".format(record["index"], record["label"], record["sentence"]))
    print("======================================================")

    ok = audit_report(records)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print("网络请求异常: {}".format(exc), file=sys.stderr)
        sys.exit(2)
    except (RuntimeError, TimeoutError) as exc:
        print("任务执行失败: {}".format(exc), file=sys.stderr)
        sys.exit(2)
