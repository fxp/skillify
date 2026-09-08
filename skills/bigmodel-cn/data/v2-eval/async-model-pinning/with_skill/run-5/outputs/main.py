#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量情感分类 —— 智谱 AI 异步对话接口（提交 + 轮询）

用法:
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

流程:
    1. POST /paas/v4/async/chat/completions  为三句话各提交一个异步任务（该接口不支持 stream）;
    2. GET  /paas/v4/async-result/{id}       轮询直到 SUCCESS / FAIL;
    3. 打印每句话的情感分类结果。

审计要求（模型版本锁定）:
    请求的模型固定为 glm-4.6。注意：智谱异步端点存在"静默换模型"的实测行为
    （glm-4.6 会被换成 glm-4.7；这种替换只发生在异步端点，同步端点不换），
    所以不能相信"请求体里写了什么就跑了什么"，必须读回响应里的 model 字段核对。
    本脚本核对两处:
      - 提交接口回显的 model（尽早发现被替换）
      - 轮询结果里的 model（权威：任务实际运行的模型）
    比较时忽略大小写（平台回显大小写不稳定，如实测请求 glm-5.3、结果回显
    GLM-5.3，属同一模型原样透传）；其余任何差异一律判为不一致，打印醒目报警，
    并以退出码 1 结束，便于审计流水线机器判定。

退出码: 0 = 全部成功且模型一致; 1 = 模型不一致或任务失败; 2 = 配置错误。
仅依赖 requests 与 Python 标准库。
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = BASE_URL + "/paas/v4/async/chat/completions"
RESULT_URL = BASE_URL + "/paas/v4/async-result"

REQUESTED_MODEL = "glm-4.6"  # 审计要求：锁定该版本，不得被静默替换

SENTENCES = [
    "这家店服务太好了，上菜快味道也棒，下次一定还来！",
    "快递拖了五天才到，包装还破了，非常失望。",
    "今天下午三点在一号会议室开项目周会。",
]

SYSTEM_PROMPT = (
    "你是一个情感分类器。对用户给出的句子判断情感倾向，"
    "只输出 正面 / 负面 / 中性 三个标签之一，不要输出任何其他内容。"
)

POLL_INTERVAL = 2    # 轮询间隔（秒）
POLL_TIMEOUT = 180   # 单个任务的轮询总超时（秒）
HTTP_TIMEOUT = 30    # 单次 HTTP 请求超时（秒）


def submit_task(sentence, api_key):
    """提交一个异步分类任务，返回 (task_id, 提交接口回显的 model)。"""
    resp = requests.post(
        SUBMIT_URL,
        headers={"Authorization": "Bearer " + api_key},
        json={
            "model": REQUESTED_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": sentence},
            ],
            # 注意：异步接口不支持 stream 参数，不要传
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "提交异步任务失败: HTTP %s, 响应: %s" % (resp.status_code, resp.text[:500]))
    body = resp.json()
    task_id = body.get("id")
    if not task_id:
        raise RuntimeError("提交响应里没有任务 id: %r" % (body,))
    return task_id, body.get("model")


def poll_result(task_id, api_key):
    """轮询异步结果直到 SUCCESS / FAIL / 超时，成功时返回完整响应体。"""
    url = RESULT_URL + "/" + task_id
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        resp = requests.get(
            url, headers={"Authorization": "Bearer " + api_key}, timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(
                "查询异步结果失败: HTTP %s, 响应: %s" % (resp.status_code, resp.text[:500]))
        result = resp.json()
        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        if status == "FAIL":
            raise RuntimeError("异步任务失败(FAIL): %r" % (result,))
        # 仍是 PROCESSING：此时响应只有 model/task_status/request_id 等壳字段，没有 choices
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "轮询超时（%ss），task_id=%s，最后状态: %s" % (POLL_TIMEOUT, task_id, status))
        time.sleep(POLL_INTERVAL)


def models_match(requested, actual):
    """审计比对：忽略大小写后必须完全一致。

    平台回显的 model 大小写不稳定（实测请求 glm-5.3、结果回显 GLM-5.3，
    属同一模型原样透传），因此纯大小写差异不算不一致；任何其他差异
    （如 glm-4.6 被换成 glm-4.7）一律判为不一致。
    """
    if not actual:
        return False
    return requested.strip().lower() == actual.strip().lower()


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误: 未设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）。\n"
              "获取地址: https://bigmodel.cn/usercenter/proj-mgmt/apikeys", file=sys.stderr)
        return 2

    print("锁定请求模型: %s" % REQUESTED_MODEL)
    print("待分类句子: %d 条" % len(SENTENCES))
    print("=" * 62)

    # ---- 第一步：批量提交（异步接口立即返回任务 id，不占用长连接） ----
    tasks = []  # (序号, 句子, task_id, 提交回显 model)
    submit_errors = []
    for idx, sentence in enumerate(SENTENCES, 1):
        try:
            task_id, echo_model = submit_task(sentence, api_key)
        except Exception as exc:
            submit_errors.append((idx, exc))
            print("[%d/%d] 提交失败: %s" % (idx, len(SENTENCES), exc))
            continue
        tasks.append((idx, sentence, task_id, echo_model))
        print("[%d/%d] 已提交  task_id=%s  提交回显 model=%s"
              % (idx, len(SENTENCES), task_id, echo_model))
    print("-" * 62)

    # ---- 第二步：逐个轮询到完成，边出结果边做模型审计 ----
    audit_fail = False
    poll_errors = []
    for idx, sentence, task_id, echo_model in tasks:
        try:
            result = poll_result(task_id, api_key)
        except Exception as exc:
            poll_errors.append((idx, exc))
            print("[%d/%d] 任务失败: %s" % (idx, len(SENTENCES), exc))
            continue

        actual_model = result.get("model")  # 权威：任务实际运行的模型
        choices = result.get("choices") or []
        if not choices:
            poll_errors.append((idx, RuntimeError("SUCCESS 但没有 choices: %r" % (result,))))
            print("[%d/%d] 任务异常: SUCCESS 但响应里没有 choices" % (idx, len(SENTENCES)))
            continue
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        finish_reason = choices[0].get("finish_reason")

        print("[%d/%d] 句子        : %s" % (idx, len(SENTENCES), sentence))
        print("      分类结果    : %s" % (content or "<空>"))
        if finish_reason != "stop":
            # 思考 token 计入 max_tokens，预算被吃光时 finish_reason=length、内容截断甚至为空
            print("      注意        : finish_reason=%s（非 stop，内容可能被截断或为空）"
                  % finish_reason)
        print("      我请求的模型 : %s" % REQUESTED_MODEL)
        print("      接口实际模型 : %s（提交回显 %s / 轮询结果回显 %s）"
              % (actual_model, echo_model, actual_model))

        if not models_match(REQUESTED_MODEL, actual_model):
            audit_fail = True
            print("      *** 模型不一致报警: 请求 %s，实际运行 %s —— 审计不通过，"
                  "本次结果不能按 glm-4.6 归档 ***" % (REQUESTED_MODEL, actual_model))
        elif not models_match(REQUESTED_MODEL, echo_model):
            # 最终结果一致但提交回显不一致：同样如实报警，供审计留痕
            audit_fail = True
            print("      *** 模型不一致报警: 提交接口回显 %s，与请求的 %s 不符 —— 审计不通过 ***"
                  % (echo_model, REQUESTED_MODEL))
        else:
            print("      模型核对    : 一致")
        print("-" * 62)

    # ---- 汇总审计结论 ----
    print("=" * 62)
    print("模型版本审计结论（要求锁定: %s）" % REQUESTED_MODEL)
    if audit_fail:
        print("!!! 警告: 存在模型不一致 —— 异步端点静默替换了模型，"
              "本次产出不能视为 glm-4.6 的结果 !!!")
    elif submit_errors or poll_errors:
        print("!!! 警告: 有任务未成功完成，模型核对未闭环，审计不能视为通过 !!!")
    else:
        print("全部任务实际运行的模型与请求一致，审计通过。")
    print("=" * 62)
    return 1 if (audit_fail or submit_errors or poll_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
