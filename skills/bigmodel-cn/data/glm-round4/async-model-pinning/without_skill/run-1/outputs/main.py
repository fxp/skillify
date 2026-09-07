#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱 GLM 异步对话接口批量情感分类（含模型版本锁定审计）。

用法:
    export ZHIPUAI_API_KEY=<你的智谱 API Key>
    python3 main.py

流程:
    1. 从环境变量 ZHIPUAI_API_KEY 读取密钥；
    2. 调用异步对话补全接口 POST /api/paas/v4/async/chat/completions，
       为三句话各提交一个情感分类任务（请求体中模型写死为 glm-4.6，不允许覆盖）；
    3. 轮询 GET /api/paas/v4/async-result/{task_id} 直到全部任务完成；
    4. 审计核对: 打印每个任务「我请求的模型」与「接口实际使用的模型」
       （实际模型取自结果响应顶层 model 字段）。只要有一项不一致、或响应里
       拿不到实际模型，都视为审计不通过: 打醒目报警并以退出码 2 结束。

退出码:
    0  全部任务完成且模型版本核对一致
    1  运行失败（密钥缺失 / 网络 / HTTP / 任务 FAIL / 轮询超时）
    2  审计报警（模型版本不一致或无法确认）
"""

import os
import sys
import time

import requests

API_KEY_ENV = "ZHIPUAI_API_KEY"
API_BASE = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = API_BASE + "/async/chat/completions"
RESULT_URL_TEMPLATE = API_BASE + "/async-result/{task_id}"

PINNED_MODEL = "glm-4.6"  # 审计要求: 锁定的模型版本，请求体里固定写死
HTTP_TIMEOUT = 30         # 单次 HTTP 请求超时（秒）
POLL_INTERVAL = 2.0       # 轮询间隔（秒）
POLL_TIMEOUT = 300.0      # 单个任务最长等待（秒）

# 待分类的三句话（正面 / 负面 / 中性 各一句）
SENTENCES = [
    "快递两天就到了，客服也特别耐心，这次购物体验非常好！",
    "屏幕有坏点，反馈了一周客服都在推脱，太让人失望了。",
    "明天上午十点在三层会议室开季度总结会。",
]

SYSTEM_PROMPT = (
    "你是情感分类助手。对用户给出的句子做情感分类，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)


def die(message, exit_code=1):
    print("[错误] " + message, file=sys.stderr)
    sys.exit(exit_code)


def get_api_key():
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        die("未设置环境变量 %s，请先: export %s=<你的智谱 API Key>" % (API_KEY_ENV, API_KEY_ENV))
    return key


def auth_headers(api_key):
    return {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }


def raise_api_error(action, resp):
    """把非 200 响应转成带平台错误码的异常信息（错误体形如 {"error":{"code","message"}}）。"""
    detail = resp.text
    try:
        err = resp.json().get("error") or {}
        detail = "%s: %s" % (err.get("code", resp.status_code), err.get("message", resp.text))
    except ValueError:
        pass
    raise RuntimeError("%s失败 HTTP %s | %s" % (action, resp.status_code, detail))


def submit_task(session, api_key, sentence):
    """提交一个异步分类任务，返回任务 id。"""
    payload = {
        "model": PINNED_MODEL,  # 审计锁定: 每个请求都明确指定 glm-4.6
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        "temperature": 0.1,               # 分类任务，尽量稳定
        "thinking": {"type": "disabled"},  # glm-4.5+ 支持，关闭思维链，直接输出分类词
        "max_tokens": 1024,
    }
    resp = session.post(SUBMIT_URL, headers=auth_headers(api_key),
                        json=payload, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise_api_error("提交任务", resp)
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError("提交任务成功但响应中没有任务 id: %r" % data)
    return task_id


def poll_task(session, api_key, task_id):
    """轮询任务结果，任务成功时返回结果 dict（含顶层 model 字段）。"""
    url = RESULT_URL_TEMPLATE.format(task_id=task_id)
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        resp = session.get(url, headers=auth_headers(api_key), timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            raise_api_error("查询任务 %s" % task_id, resp)
        data = resp.json()
        status = data.get("task_status")
        if status == "FAIL":
            raise RuntimeError("任务 %s 执行失败: %r" % (task_id, data))
        # SUCCESS 即完成；个别情况下响应未带 task_status 但已带 choices，同样视为完成
        if status == "SUCCESS" or (status is None and data.get("choices")):
            return data
        if time.monotonic() >= deadline:
            raise RuntimeError("任务 %s 超过 %.0f 秒仍未完成（最后状态 %s）"
                               % (task_id, POLL_TIMEOUT, status or "未知"))
        time.sleep(POLL_INTERVAL)


def extract_answer(result, task_id):
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("任务 %s 的结果中没有 choices: %r" % (task_id, result))
    return ((choices[0].get("message") or {}).get("content") or "").strip()


def main():
    api_key = get_api_key()
    results = []  # [(句子, 分类结果, 接口实际使用的模型), ...]

    with requests.Session() as session:
        # 第一步: 批量提交三句话的分类任务
        task_ids = []
        for i, sentence in enumerate(SENTENCES, 1):
            task_id = submit_task(session, api_key, sentence)
            print("[提交] 第 %d 句 -> task_id=%s" % (i, task_id))
            task_ids.append(task_id)

        # 第二步: 逐个轮询，收齐结果
        for i, (task_id, sentence) in enumerate(zip(task_ids, SENTENCES), 1):
            result = poll_task(session, api_key, task_id)
            label = extract_answer(result, task_id)
            served_model = (result.get("model") or "").strip()  # 接口实际使用的模型
            results.append((sentence, label, served_model))
            print("[完成] 第 %d 句 -> 分类结果: %s" % (i, label))

    # 第三步: 打印分类结果
    print("\n========== 情感分类结果 ==========")
    for i, (sentence, label, _) in enumerate(results, 1):
        print("%d. %s\n   -> %s" % (i, sentence, label))

    # 第四步: 模型版本审计核对（请求模型 vs 接口实际使用的模型）
    print("\n========== 模型版本审计核对 ==========")
    mismatches = []
    for i, (_, _, served_model) in enumerate(results, 1):
        if not served_model:
            # 拿不到实际模型 = 无法证明用的是 glm-4.6，审计上同样不能放过
            mismatches.append((i, "<响应未返回 model 字段>"))
            mark = "[无法确认 => 报警]"
        elif served_model == PINNED_MODEL:
            mark = "[一致]"
        else:
            mismatches.append((i, served_model))
            mark = "[不一致 => 报警]"
        print("任务 %d: 我请求的模型=%s | 接口实际使用的模型=%s | %s"
              % (i, PINNED_MODEL, served_model or "<未返回>", mark))

    if mismatches:
        print("\n" + "!" * 70)
        print("!!!!! [审计报警] 模型版本锁定不通过 !!!!!")
        for i, actual in mismatches:
            print("!!!!! 任务 %d: 请求 %s，但接口实际使用的是「%s」" % (i, PINNED_MODEL, actual))
        print("!!!!! 本次运行结果不可用于审计，请立即排查（模型可能被平台侧替换或别名指向了其他版本）。")
        print("!" * 70)
        sys.exit(2)

    print("\n审计结论: %d 个任务的「请求模型」与「接口实际使用模型」全部一致，均为 %s。"
          % (len(results), PINNED_MODEL))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        die("网络请求异常: %s" % exc)
    except RuntimeError as exc:
        die(str(exc))
