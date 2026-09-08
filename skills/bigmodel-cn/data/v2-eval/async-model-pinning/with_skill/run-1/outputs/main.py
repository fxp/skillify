# -*- coding: utf-8 -*-
"""用智谱 AI 开放平台的【异步】对话接口对三句话做情感分类（批量任务）。

流程（异步两步走）：
  1. POST /paas/v4/async/chat/completions   提交任务，拿到任务 id
  2. GET  /paas/v4/async-result/{id}        轮询，直到 task_status 变为 SUCCESS / FAIL

审计要求：本任务锁定模型 glm-4.6。已知陷阱（实测验证）：异步端点可能【静默替换模型】
（例如请求 glm-4.6 实际跑 glm-4.7），HTTP 层面不报任何错。因此脚本在提交回执和轮询
结果两处都读回响应体的 `model` 字段，与请求的模型核对；任何一处不一致都明确报警，
并以退出码 1 结束，绝不含糊。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = f"{BASE_URL}/async/chat/completions"
RESULT_URL = f"{BASE_URL}/async-result"  # 轮询时拼 /{task_id}

# 审计锁定的模型版本：请求它，并核对接口实际使用的就是它
REQUESTED_MODEL = "glm-4.6"

# 待分类的三句话
SENTENCES = [
    "这家店的服务的确很周到，下次还会再来。",
    "物流太慢了，包装也破损，体验很差。",
    "我今天下午去了趟超市买了一瓶酱油。",
]

POLL_INTERVAL = 2      # 轮询间隔（秒）
POLL_TIMEOUT = 180     # 单个任务轮询总超时（秒）
HTTP_TIMEOUT = 30      # 单次 HTTP 请求超时（秒）


def submit_async_task(api_key, sentence):
    """提交一个异步对话任务，返回 (task_id, 提交回执里回显的 model)。"""
    payload = {
        "model": REQUESTED_MODEL,
        # 注意：异步接口不支持 stream 参数（本身就是提交+轮询模式）
        "messages": [
            {
                "role": "system",
                "content": "你是情感分类器。对用户给出的句子判断情感倾向，"
                           "只输出「正面」「负面」「中性」三个词之一，不要输出任何其他内容。",
            },
            {"role": "user", "content": sentence},
        ],
        "temperature": 0.1,
    }
    resp = requests.post(
        SUBMIT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    task_id = body.get("id")
    if not task_id:
        raise RuntimeError(f"提交异步任务失败，响应中没有任务 id：{body}")
    return task_id, body.get("model", "")


def poll_async_result(api_key, task_id):
    """轮询异步结果，SUCCESS 时返回完整响应体，FAIL / 超时则抛异常。"""
    url = f"{RESULT_URL}/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    waited = 0
    while waited < POLL_TIMEOUT:
        r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        body = r.json()
        status = body.get("task_status")
        # 兼容：个别情况下对话结果不回 task_status，而是直接带 choices
        if status == "SUCCESS" or (status is None and "choices" in body):
            return body
        if status == "FAIL":
            raise RuntimeError(f"异步任务 {task_id} 失败（task_status=FAIL）：{body}")
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL
    raise TimeoutError(f"轮询异步任务 {task_id} 超时（>{POLL_TIMEOUT}s）")


def extract_label(content):
    """从模型回复里提取情感标签；模型没按格式答时给出可读的兜底。"""
    for label in ("正面", "负面", "中性"):
        if label in content:
            return label
    return f"无法解析（原始回复：{content.strip()!r}）"


def audit_check(idx, sentence, submit_model, result_model):
    """核对「我请求的模型」与「接口实际使用的模型」。

    平台回显的 model 大小写不统一（如 glm-4.7 vs GLM-4.7），同一模型的大小写
    差异不算替换，故按忽略大小写比较；但会原样打印两个回显值供审计留痕。
    返回 True 表示一致，False 表示不一致（已报警）。
    """
    print(f"  [审计] 请求的模型     : {REQUESTED_MODEL}")
    print(f"  [审计] 提交回执回显   : {submit_model or '(未返回)'}")
    print(f"  [审计] 结果响应回显   : {result_model or '(未返回)'}")

    problems = []
    if submit_model and submit_model.strip().lower() != REQUESTED_MODEL.lower():
        problems.append(f"提交回执回显为 {submit_model}")
    if result_model and result_model.strip().lower() != REQUESTED_MODEL.lower():
        problems.append(f"结果响应回显为 {result_model}")
    if not submit_model and not result_model:
        problems.append("两处响应均未回显 model 字段，无法核对")

    if problems:
        print(f"  ⚠️  ⚠️  ⚠️  模型不一致报警（第 {idx} 句：{sentence}）")
        print(f"  ⚠️  审计要求锁定 {REQUESTED_MODEL}，但 {'；'.join(problems)}。")
        print( "  ⚠️  异步端点未按请求模型执行，本条结果不可用于版本锁定的审计场景！")
        return False
    print("  [审计] 核对通过：接口实际使用的模型与请求一致。")
    return True


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ZHIPUAI_API_KEY，请先 export ZHIPUAI_API_KEY=你的Key",
              file=sys.stderr)
        sys.exit(2)

    print(f"批量情感分类（异步接口）开始，共 {len(SENTENCES)} 句。")
    print(f"审计锁定模型：{REQUESTED_MODEL}\n")

    mismatches = []
    for idx, sentence in enumerate(SENTENCES, 1):
        print(f"[{idx}/{len(SENTENCES)}] 文本：{sentence}")
        try:
            task_id, submit_model = submit_async_task(api_key, sentence)
            print(f"  已提交异步任务 task_id={task_id}（提交回显 model={submit_model}）")

            result = poll_async_result(api_key, task_id)
            result_model = result.get("model", "")
            choice = result["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"].get("content") or ""
            print(f"  轮询完成 task_status=SUCCESS finish_reason={finish_reason}")

            if finish_reason == "length":
                print("  ⚠️ finish_reason=length：输出被截断，分类结果可能不完整。")
            label = extract_label(content)
            print(f"  分类结果：{label}")

            ok = audit_check(idx, sentence, submit_model, result_model)
            if not ok:
                mismatches.append((idx, sentence, REQUESTED_MODEL, result_model or submit_model))
        except (requests.RequestException, RuntimeError, TimeoutError, KeyError, IndexError) as exc:
            print(f"  ❌ 第 {idx} 句处理失败：{exc}")
            mismatches.append((idx, sentence, REQUESTED_MODEL, "处理失败，未获得结果"))
        print()

    print("=" * 60)
    print("审计核对汇总")
    print(f"  请求的模型     ：{REQUESTED_MODEL}")
    if mismatches:
        print(f"  ⚠️  发现 {len(mismatches)} 处模型不一致 / 失败，明细：")
        for idx, sentence, requested, actual in mismatches:
            print(f"    - 第 {idx} 句（{sentence}）：请求 {requested}，实际 {actual}")
        print("  ⚠️  审计报警：异步接口未按锁定的模型版本执行，请勿将本次结果用于审计口径！")
        sys.exit(1)
    print("  全部任务模型核对一致，符合审计要求。")
    print("=" * 60)


if __name__ == "__main__":
    main()
