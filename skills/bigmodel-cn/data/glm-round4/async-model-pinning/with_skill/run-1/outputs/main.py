"""批量情感分类——智谱异步对话接口版。

流程：把三句话全部提交到 POST /paas/v4/async/chat/completions 拿 task_id，
再逐个轮询 GET /paas/v4/async-result/{id} 直到 SUCCESS/FAIL。

审计要求：模型版本必须锁定 glm-4.6。脚本会同时打印
「我请求的模型」和「接口实际使用的模型」（提交响应回显 + 轮询结果两处），
任一任务的实际模型与请求不一致时，明确报警并以退出码 1 结束。

用法：
    ZHIPUAI_API_KEY=你的key python3 main.py
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"

REQUESTED_MODEL = "glm-4.6"  # 审计要求锁定的模型版本，不得改动

SENTENCES = [
    "快递第二天就到了，包装也很仔细，非常满意！",
    "客服态度敷衍，问题拖着一直不解决，太让人失望了。",
    "今天下午三点在会议室开项目复盘会。",
]

SYSTEM_PROMPT = (
    "你是情感分类器。判断用户句子的情感倾向，"
    "只输出 positive、negative、neutral 三个英文单词中的一个，不要输出任何其他内容。"
)

VALID_LABELS = ("positive", "negative", "neutral")

POLL_INTERVAL_SECONDS = 2   # 官方未规定轮询间隔，2-5 秒固定间隔即可
POLL_TIMEOUT_SECONDS = 180  # 单个任务的总轮询时长上限，防止死循环
HTTP_TIMEOUT_SECONDS = 30


def auth_headers():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY，无法调用智谱接口。")
    return {"Authorization": f"Bearer {api_key}"}


def submit_task(headers, text):
    """提交一个异步分类任务，返回 (task_id, 提交响应回显的 model)。

    提交响应的 model 字段官方语义是「此次调用使用的名称」，不是请求值的
    原样回声，所以它就是第一个要核对的「实际使用模型」信号。
    """
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        # 审计要求结果可复现：贪心解码，降低采样随机性
        "do_sample": False,
        "max_tokens": 1024,
    }
    resp = requests.post(
        SUBMIT_URL,
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"提交任务失败 HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("task_status") != "PROCESSING":
        raise RuntimeError(f"提交任务返回异常状态: {data}")
    return data["id"], data.get("model")


def poll_result(headers, task_id):
    """轮询异步结果直到 SUCCESS / FAIL / 超时，成功时返回完整响应 dict。"""
    url = f"{BASE_URL}/paas/v4/async-result/{task_id}"
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while True:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            raise RuntimeError(f"查询任务 {task_id} 失败 HTTP {resp.status_code}: {resp.text}")
        result = resp.json()
        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        if status == "FAIL":
            raise RuntimeError(f"异步任务 {task_id} 失败: {result}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"轮询任务 {task_id} 超时（>{POLL_TIMEOUT_SECONDS}s），最后状态: {status}"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def extract_label(result):
    """从轮询结果提取情感标签；模型输出可能夹带标点/大小写，做归一化容错。"""
    choices = result.get("choices") or []
    content = ""
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
    text = content.strip().lower()
    for label in VALID_LABELS:
        if label in text:
            return label
    return text or "(模型未返回内容)"


def main():
    headers = auth_headers()

    print(f"我请求的模型（审计锁定版本）: {REQUESTED_MODEL}")
    print(f"待分类句子数: {len(SENTENCES)}")
    print()

    # 阶段一：批量提交（串行提交，避免触发并发速率限制）
    tasks = []  # [(句子, task_id, 提交回显 model)]
    for i, sentence in enumerate(SENTENCES, 1):
        task_id, echoed_model = submit_task(headers, sentence)
        tasks.append((sentence, task_id, echoed_model))
        print(f"[{i}/{len(SENTENCES)}] 已提交 task_id={task_id}，提交回显 model={echoed_model!r}")

    # 阶段二：逐个轮询拿结果
    print()
    results = []  # [(序号, 句子, 标签, 提交回显 model, 结果 model)]
    for i, (sentence, task_id, echoed_model) in enumerate(tasks, 1):
        result = poll_result(headers, task_id)
        label = extract_label(result)
        actual_model = result.get("model")
        results.append((i, sentence, label, echoed_model, actual_model))
        print(f"[{i}/{len(SENTENCES)}] {sentence}")
        print(f"        情感: {label} | 实际使用模型: {actual_model!r}")

    # 阶段三：模型版本审计核对。
    # 平台回显的大小写不稳定（实测 glm-4.5-air 会回显成 GLM-4.5-Air），
    # 大小写差异不算换模型，因此比较前统一小写。
    print()
    print("=" * 62)
    print("模型版本审计核对")
    print("=" * 62)
    print(f"我请求的模型       : {REQUESTED_MODEL}")

    requested = REQUESTED_MODEL.strip().lower()
    mismatches = []
    for i, sentence, label, echoed_model, actual_model in results:
        echoed = (echoed_model or "").strip().lower()
        actual = (actual_model or "").strip().lower()
        if echoed != requested or actual != requested:
            mismatches.append((i, echoed_model, actual_model))
            print(f"任务{i}: 提交回显={echoed_model!r} / 结果model={actual_model!r} -> 不一致 (MISMATCH)")
        else:
            print(f"任务{i}: 提交回显={echoed_model!r} / 结果model={actual_model!r} -> 一致 (OK)")

    if not mismatches:
        print()
        print(f"[审计通过] 全部 {len(results)} 个任务实际使用的模型均为 {REQUESTED_MODEL}。")
        return 0

    print()
    print("!" * 62)
    print("⚠️  审计报警：接口实际使用的模型与请求的模型不一致！")
    print(f"    我请求的模型   : {REQUESTED_MODEL}")
    for i, echoed_model, actual_model in mismatches:
        print(f"    任务{i} 实际使用 : 提交回显={echoed_model!r} / 结果model={actual_model!r}")
    print("    本批次不满足「锁定 glm-4.6」的审计要求，结果不可用于审计留痕，")
    print("    请人工核查（智谱异步端点存在静默替换模型版本的行为）。")
    print("!" * 62)
    return 1


if __name__ == "__main__":
    sys.exit(main())
