#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱 AI 异步对话接口：批量情感分类 + 模型版本锁定审计。

流程（标准 API，Base URL https://open.bigmodel.cn/api/，Bearer 鉴权）：
  1. POST /paas/v4/async/chat/completions   逐句提交异步任务，拿 task_id；
  2. GET  /paas/v4/async-result/{task_id}   轮询到任务完成，取回分类结果；
  3. 审计核对：打印「请求体里写的模型」与「接口回显实际使用的模型」，
     不一致（忽略大小写）则打印醒目告警并以退出码 2 结束。

为什么必须做第 3 步：智谱**异步**端点存在"静默换模型"行为——实测请求
glm-4.6 会被换成 glm-4.7 执行（换成的 glm-4.7-ali 等名字甚至不在官方
文档里），同步端点则原样透传。因此有版本锁定 / 审计对账要求时不能相信
请求体，必须读回响应里的 model 字段核对。回显大小写不统一（如请求
glm-4.5-air 回显 GLM-4.5-Air），故比较时忽略大小写，只抓真正的换版本。

运行：ZHIPUAI_API_KEY=你的Key python3 main.py
退出码：0 全部成功且模型核对通过；1 环境/接口错误；2 模型版本不一致。
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = BASE_URL + "/paas/v4/async/chat/completions"
RESULT_URL = BASE_URL + "/paas/v4/async-result"

# 审计要求：锁定 glm-4.6。注意异步端点实测会把它静默替换成 glm-4.7，
# 本脚本的任务之一就是把这种替换明确暴露出来，而不是让它无声通过。
REQUESTED_MODEL = "glm-4.6"

POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 30

SENTENCES = [
    "今天天气真好，和朋友爬山看了日落，一整天都特别开心！",
    "快递拖了一个星期才到，包装还破了，客服处理问题的态度也很敷衍，太失望了。",
    "我下班顺路在楼下便利店买了一瓶矿泉水。",
]

SYSTEM_PROMPT = (
    "你是文本情感分类器。对用户给出的句子判断情感倾向，"
    "只输出 positive、negative、neutral 三个标签之一，不要输出任何其他内容。"
)


def _headers(api_key):
    return {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }


def _check_http(resp):
    """HTTP 层错误检查：优先透出平台返回的 error.code / error.message。"""
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            detail = " code={0} message={1}".format(err.get("code"), err.get("message"))
        except ValueError:
            detail = " " + resp.text[:200]
        raise RuntimeError("HTTP {0}{1}".format(resp.status_code, detail))
    return resp


def submit_async(sentence, api_key):
    """提交一个异步分类任务。返回 (task_id, 提交响应回显的 model, task_status)。"""
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": sentence},
        ],
        "max_tokens": 1024,  # 官方建议 >=1024；思考 token 也计入该预算，给太小会拿到空内容
        # 注意：异步接口不支持 stream 参数（本身就是提交+轮询模式）
    }
    resp = _check_http(
        requests.post(SUBMIT_URL, headers=_headers(api_key), json=payload,
                      timeout=HTTP_TIMEOUT_SECONDS)
    )
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError("提交异步任务未返回任务 id：{0}".format(data))
    return task_id, data.get("model"), data.get("task_status")


def poll_result(task_id, api_key):
    """轮询异步结果直到成功 / 失败 / 超时，返回最终响应 dict。"""
    url = "{0}/{1}".format(RESULT_URL, task_id)
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        data = _check_http(
            requests.get(url, headers=_headers(api_key), timeout=HTTP_TIMEOUT_SECONDS)
        ).json()
        status = data.get("task_status")
        if status == "FAIL":
            raise RuntimeError("异步任务失败（task_status=FAIL）：{0}".format(data))
        # 成功判定兼容两种响应形态：官方 OpenAPI 里对话补全的最终结果不带
        # task_status、只带 choices；平台实测也可能在 SUCCESS 时同时给出两者。
        if status == "SUCCESS" or "choices" in data:
            return data
        # 其余情况为 PROCESSING（壳响应无 choices），继续轮询
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError("轮询超时（>{0}s）：task_id={1}".format(POLL_TIMEOUT_SECONDS, task_id))


def models_match(requested, echoed):
    """版本一致性比较：忽略大小写与首尾空白。

    大小写差异不算换模型（请求 glm-4.5-air 官方即回显 GLM-4.5-Air），
    glm-4.6 vs glm-4.7 这种才是审计要抓的；接口没回显 model 同样视为不通过。
    """
    if not echoed:
        return False
    return requested.strip().lower() == echoed.strip().lower()


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "错误：未检测到环境变量 ZHIPUAI_API_KEY。\n"
            "请先在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取标准 API Key，\n"
            "然后运行：ZHIPUAI_API_KEY=你的Key python3 main.py"
        )

    print("批量情感分类（智谱异步对话接口）：共 {0} 句".format(len(SENTENCES)))
    print("审计要求锁定的模型：{0}\n".format(REQUESTED_MODEL))

    # ---- 第 1 步：逐句提交异步任务，先拿全 task_id（异步批处理的标准姿势） ----
    tasks = []
    for i, sentence in enumerate(SENTENCES, 1):
        task_id, submit_model, status = submit_async(sentence, api_key)
        print("[{0}/{1}] 已提交 task_id={2} task_status={3} 提交回显 model={4!r}".format(
            i, len(SENTENCES), task_id, status, submit_model))
        tasks.append({
            "index": i,
            "sentence": sentence,
            "task_id": task_id,
            "submit_model": submit_model,
        })

    # ---- 第 2 步：逐个轮询取回最终结果 ----
    print("\n轮询异步结果……")
    for task in tasks:
        result = poll_result(task["task_id"], api_key)
        task["result_model"] = result.get("model")
        choice = result["choices"][0]
        task["finish_reason"] = choice.get("finish_reason")
        task["label"] = (choice.get("message", {}).get("content") or "").strip()
        print("[{0}/{1}] task_id={2} 完成 finish_reason={3} 结果回显 model={4!r}".format(
            task["index"], len(tasks), task["task_id"], task["finish_reason"], task["result_model"]))
        if task["finish_reason"] != "stop":
            print("    注意：finish_reason 非 stop（可能被截断或命中内容过滤），结果仅供参考")

    # ---- 第 3 步：输出分类结果 ----
    print("\n" + "=" * 68)
    print("情感分类结果")
    print("=" * 68)
    for task in tasks:
        print("{0}. {1}".format(task["index"], task["sentence"]))
        print("   -> {0}".format(task["label"] or "（空结果）"))

    # ---- 第 4 步：模型版本审计核对（本脚本的核心要求） ----
    print("\n" + "=" * 68)
    print("模型版本审计核对：我请求的模型 vs 接口实际使用的模型")
    print("=" * 68)
    print("我请求的模型（请求体 model 字段）: {0}".format(REQUESTED_MODEL))

    mismatches = []
    for task in tasks:
        submit_ok = models_match(REQUESTED_MODEL, task.get("submit_model"))
        result_ok = models_match(REQUESTED_MODEL, task.get("result_model"))
        if not (submit_ok and result_ok):
            mismatches.append(task)
        print("任务 {0}（task_id={1}）：".format(task["index"], task["task_id"]))
        print("  提交接口回显的 model（POST /async/chat/completions）: {0!r}  -> {1}".format(
            task.get("submit_model"), "一致" if submit_ok else "不一致"))
        print("  结果接口回显的 model（GET  /async-result/{{id}}）    : {0!r}  -> {1}".format(
            task.get("result_model"), "一致" if result_ok else "不一致"))

    actual_models = sorted(
        {m for t in tasks for m in (t.get("submit_model"), t.get("result_model")) if m}
    )
    print("\n接口实际使用的模型（去重）: {0}".format(", ".join(actual_models) or "（无回显）"))

    if mismatches:
        print()
        print("!" * 68)
        print("审计告警：模型版本不一致——接口实际使用的模型与请求的不符！")
        print("!" * 68)
        for task in mismatches:
            print("  任务 {0}：请求 {1!r}，提交回显 {2!r}，结果回显 {3!r}".format(
                task["index"], REQUESTED_MODEL, task.get("submit_model"), task.get("result_model")))
        print("  背景：智谱异步端点存在静默换模型行为（实测 glm-4.6 会被换成")
        print("  glm-4.7 执行，同步端点不换）。本次运行不满足「锁定 {0}」的".format(REQUESTED_MODEL))
        print("  审计要求，上述分类结果不得用于审计口径。脚本以退出码 2 结束。")
        return 2

    print("\n核对通过：所有任务实际使用的模型与请求的模型一致。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (requests.RequestException, RuntimeError, TimeoutError) as exc:
        print("\n执行失败：{0}".format(exc), file=sys.stderr)
        sys.exit(1)
