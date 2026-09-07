#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智谱 GLM 异步对话接口：批量情感分类 + 模型版本审计。

流程（智谱标准 API，HTTP Bearer 鉴权，仅依赖 requests）：
  1. 对每句话 POST /paas/v4/async/chat/completions 提交异步任务，拿到任务 id；
     （异步接口不支持 stream，请求体不传该参数）
  2. 轮询 GET /paas/v4/async-result/{id}，直到 task_status 变为 SUCCESS / FAIL；
  3. 解析每句话的情感分类结果；
  4. 【审计】核对"我请求的模型"与"接口实际使用的模型"：
     - 提交接口响应的 model 字段（提交回显）
     - 轮询结果响应的 model 字段（结果回显）
     两者任一与请求值不一致、或字段缺失，都打印醒目报警并以非零码退出。

为什么必须做第 4 步：异步端点已被实测会静默替换模型——请求体写 glm-4.6，
服务端实际可能跑 glm-4.7（提交回显 glm-4.7、结果回显 GLM-4.7），同步端点则不会。
有审计/对账要求的场景不能相信请求体，必须读回响应回显核对。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys
import time
import uuid

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"
RESULT_URL = f"{BASE_URL}/paas/v4/async-result/{{task_id}}"

# 审计要求锁定的模型版本。glm-4.6 为有效模型代码（200K 上下文 / 128K 最大输出），
# 不要改成 glm-4.6v / glm-4.6v-flash 等相似名字。
REQUESTED_MODEL = "glm-4.6"

# 批量任务：三句话情感分类
SENTENCES = [
    "这家餐厅的菜品太好吃了，服务也特别贴心，下次一定还来！",
    "快递拖了整整一个星期才到，包装还破损了，非常失望。",
    "明天下午三点在二楼会议室开项目周会，请大家准时参加。",
]

POLL_INTERVAL = 2    # 轮询间隔（秒），官方建议 2-5 秒
POLL_TIMEOUT = 300   # 单个任务轮询总超时（秒），避免死循环
HTTP_TIMEOUT = 30    # 单次 HTTP 请求超时（秒）

# 用 json_object 模式约束输出（平台不支持 json_schema 强约束），
# 目标结构必须写进 prompt；客户端仍需容忍夹带文字、做解析兜底。
SYSTEM_PROMPT = (
    "你是情感分类助手。对用户给出的句子判断情感倾向，"
    "只输出一个 JSON 对象，不要输出任何解释或其他文字，格式为："
    '{"sentiment": "positive 或 negative 或 neutral", "confidence": 0到1之间的小数}。'
    "positive=正面，negative=负面，neutral=中性。"
)


def check_api_response(resp: requests.Response, action: str) -> dict:
    """统一处理 HTTP 错误与业务错误（响应体 {"error": {"code", "message"}}）。"""
    if not resp.ok:
        raise RuntimeError(f"{action} 失败：HTTP {resp.status_code} {resp.text}")
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        raise RuntimeError(f"{action} 失败：业务错误 code={err.get('code')} message={err.get('message')}")
    return data


def submit_async_task(api_key: str, sentence: str) -> dict:
    """提交一个异步分类任务，返回提交响应（含 id / model / task_status）。"""
    request_id = uuid.uuid4().hex  # 便于审计追溯提交与结果的对应关系
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请分类这句话：{sentence}"},
        ],
        "response_format": {"type": "json_object"},
        "do_sample": False,   # 贪心解码，分类结果可复现（审计友好）
        "max_tokens": 512,    # 显式限制输出长度，glm 系列默认值高达 65536
        "request_id": request_id,
    }
    resp = requests.post(
        SUBMIT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=HTTP_TIMEOUT,
    )
    return check_api_response(resp, "提交异步任务")


def poll_async_result(api_key: str, task_id: str) -> dict:
    """轮询任务结果，SUCCESS 返回完整结果 dict，FAIL/超时抛异常。"""
    url = RESULT_URL.format(task_id=task_id)
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + POLL_TIMEOUT
    status = None
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        result = check_api_response(resp, "查询异步结果")
        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        if status == "FAIL":
            raise RuntimeError(f"异步任务 {task_id} 失败：{json.dumps(result, ensure_ascii=False)}")
        # PROCESSING：继续等
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"轮询任务 {task_id} 超时（>{POLL_TIMEOUT}s），最后状态：{status}")


def parse_sentiment(raw: str):
    """解析模型输出。json_object 模式不保证 100% 合法 JSON，做一次截取兜底。"""
    if not raw:
        return None
    candidates = [raw]
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])  # 剥掉可能夹带的说明文字
    for text in candidates:
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("sentiment") in ("positive", "negative", "neutral"):
            return obj
    return None


def norm_model(model) -> str:
    """归一化模型名用于比对。

    平台回显的大小写不统一（实测请求 glm-4.5-air 会回显 GLM-4.5-Air，同一模型），
    所以按小写比较避免误报；但这不影响抓出真正的版本替换（glm-4.6 != glm-4.7）。
    """
    return (model or "").strip().lower()


def run_audit(records) -> bool:
    """核对每个任务的请求模型与实际使用模型，全部一致返回 True。"""
    print("\n" + "=" * 68)
    print(f"[模型版本审计] 请求锁定的模型：{REQUESTED_MODEL}")
    print("=" * 68)
    all_match = True
    for rec in records:
        # 两个回显都要核对：提交回显与结果回显理论上应一致，且都等于请求值
        for source, actual in (("提交接口回显 model", rec["submit_model"]),
                               ("轮询结果回显 model", rec["result_model"])):
            if actual is None:
                all_match = False
                print(f'  [任务{rec["idx"]}] {source}: 字段缺失，无法核验 —— 审计失败')
            elif norm_model(actual) != norm_model(REQUESTED_MODEL):
                all_match = False
                print(f'  [任务{rec["idx"]}] {source}: {actual} != 请求的 {REQUESTED_MODEL} —— 不一致')
            else:
                print(f'  [任务{rec["idx"]}] {source}: {actual} == {REQUESTED_MODEL} —— 一致')

    print("-" * 68)
    if all_match:
        print(f"[审计通过] 所有任务实际使用的模型均为 {REQUESTED_MODEL}，与请求一致。")
    else:
        print("!!" * 34)
        print("【审计报警 / AUDIT ALERT】模型版本不一致！")
        print(f"  我请求的模型           : {REQUESTED_MODEL}")
        for rec in records:
            print(f'  任务{rec["idx"]} 接口实际使用的模型: '
                  f'提交回显={rec["submit_model"]!r}, 结果回显={rec["result_model"]!r}')
        print("  审计要求锁定 glm-4.6，实际执行模型与之不符，本次结果不可用于审计留痕。")
        print("!!" * 34)
    return all_match


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=你的Key",
              file=sys.stderr)
        return 1

    print(f"批量情感分类开始：{len(SENTENCES)} 句，异步接口，锁定模型 {REQUESTED_MODEL}")

    # 第一步：先把所有任务提交出去（服务端并行处理），再逐个轮询
    records = []
    for idx, sentence in enumerate(SENTENCES, start=1):
        submit = submit_async_task(api_key, sentence)
        task_id = submit.get("id")
        if not task_id:
            raise RuntimeError(f"任务{idx} 提交响应中没有任务 id：{submit}")
        records.append({
            "idx": idx,
            "sentence": sentence,
            "task_id": task_id,
            "request_id": submit.get("request_id"),
            "submit_model": submit.get("model"),   # 提交回显：此次调用使用的模型
        })
        print(f'  任务{idx} 已提交：task_id={task_id} task_status={submit.get("task_status")} '
              f'提交回显 model={submit.get("model")}')

    # 第二步：轮询拿结果并解析
    for rec in records:
        result = poll_async_result(api_key, rec["task_id"])
        rec["result_model"] = result.get("model")  # 结果回显：实际生成内容的模型
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        rec["finish_reason"] = choice.get("finish_reason")
        parsed = parse_sentiment(message.get("content"))
        rec["raw_content"] = message.get("content")
        rec["parsed"] = parsed

    # 第三步：打印分类结果
    print("\n[分类结果]")
    for rec in records:
        parsed = rec["parsed"]
        if parsed:
            sentiment_cn = {"positive": "正面", "negative": "负面", "neutral": "中性"}
            label = parsed["sentiment"]
            print(f'  任务{rec["idx"]} {sentiment_cn.get(label, label)}'
                  f'（confidence={parsed.get("confidence")}）'
                  f' finish_reason={rec["finish_reason"]}')
            print(f'         句子：{rec["sentence"]}')
        else:
            print(f'  任务{rec["idx"]} 解析失败，模型原始输出：{rec["raw_content"]!r}')

    # 第四步：模型版本审计（本脚本的核心交付），不一致以非零码退出
    ok = run_audit(records)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
