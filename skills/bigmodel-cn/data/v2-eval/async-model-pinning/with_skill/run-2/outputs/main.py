#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量情感分类 —— 智谱异步对话接口 + 模型版本锁定审计。

流程：
  1. 用 POST /paas/v4/async/chat/completions 一次性提交 3 个情感分类任务；
  2. 用 GET /paas/v4/async-result/{id} 轮询每个任务直到 SUCCESS / FAIL；
  3. 审计核对：打印「我请求的模型」与「接口实际使用的模型」（取自提交回显
     和最终结果回显的 model 字段），两者不一致时明确报警并以退出码 1 结束。

为什么必须读回 model 字段核对：智谱的**异步**端点会静默替换模型
（实测 glm-4.6 会被换成 glm-4.7，同步端点不换），请求体里写什么不等于
实际跑什么。有版本锁定/审计要求时，唯一可信的依据是响应回显的 model。

模型名比对按忽略大小写处理：平台回显的大小写不统一（如 glm-5.3 会回显成
GLM-5.3），版本身份相同；但回显的原始字符串会原样打印进审计输出，不做遮掩。

退出码：0 = 全部成功且模型一致；1 = 存在模型不一致（审计警报）；2 = 配置或
接口调用失败。

依赖：仅 requests（API Key 从环境变量 ZHIPUAI_API_KEY 读取，绝不硬编码）。
"""

import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
SUBMIT_URL = f"{BASE_URL}/async/chat/completions"
RESULT_URL = f"{BASE_URL}/async-result"  # GET {RESULT_URL}/{task_id}

# 审计要求：本次批量任务必须锁定 glm-4.6，不允许平台侧静默升级/替换。
REQUESTED_MODEL = "glm-4.6"

# 待分类的三句话（正面 / 负面 / 中性各一）。
SENTENCES = [
    "这家店的菜品非常好吃，服务也特别热情，下次还会再来。",
    "快递迟了三天，包装还破了，客服一直在推脱，太让人失望了。",
    "今天下午三点在二楼会议室有一个项目进度回顾会。",
]

SYSTEM_PROMPT = (
    "你是情感分类器。对用户给出的句子判断情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何其他内容。"
)

POLL_INTERVAL = 2    # 轮询间隔（秒）
POLL_TIMEOUT = 120   # 单个任务的总轮询超时（秒）
HTTP_TIMEOUT = 30    # 单次 HTTP 请求超时（秒）


def normalize_model(name):
    """归一化模型名用于比对（仅去空白 + 转小写，见模块 docstring 说明）。"""
    return (name or "").strip().lower()


def auth_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def describe_http_error(resp):
    """把 HTTP 错误响应拼成可读信息，尽量带出平台返回的 code/message。"""
    try:
        body = resp.json()
        err = body.get("error") or body
        return f"HTTP {resp.status_code} code={err.get('code')} message={err.get('message')}"
    except ValueError:
        return f"HTTP {resp.status_code} body={resp.text[:200]!r}"


def submit_task(text, api_key):
    """提交一个异步分类任务，返回 (task_id, 提交接口回显的 model)。"""
    payload = {
        "model": REQUESTED_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,   # 分类任务要稳定，随机性压到最低
        "max_tokens": 1024,   # 思考 token 也计入 max_tokens，预算留足
        # 注意：异步接口不支持 stream 参数，本身就是"提交 + 轮询"模式
    }
    resp = requests.post(SUBMIT_URL, headers=auth_headers(api_key),
                         json=payload, timeout=HTTP_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"提交异步任务失败：{describe_http_error(resp)}")
    body = resp.json()
    task_id = body.get("id")
    if not task_id:
        raise RuntimeError(f"提交异步任务成功但未返回任务 id：{body}")
    return task_id, body.get("model")


def poll_result(task_id, api_key):
    """轮询异步结果直到 SUCCESS / FAIL / 超时，返回最终响应体。"""
    url = f"{RESULT_URL}/{task_id}"
    waited = 0
    while True:
        resp = requests.get(url, headers=auth_headers(api_key),
                            timeout=HTTP_TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError(f"查询异步结果失败：{describe_http_error(resp)}")
        result = resp.json()
        status = result.get("task_status")
        if status == "SUCCESS":
            return result
        if status == "FAIL":
            raise RuntimeError(f"异步任务失败（task_status=FAIL）：{result}")
        if waited >= POLL_TIMEOUT:
            raise TimeoutError(
                f"轮询超时（>{POLL_TIMEOUT}s）：task_id={task_id} 最后状态={status}")
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL


def extract_content(result, task_id):
    """从成功结果里取出分类文本；内容为空时给出含 finish_reason 的提示。"""
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"任务 {task_id} 返回 SUCCESS 但没有 choices：{result}")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")
    if not content:
        # finish_reason=length 多为思考 token 吃光 max_tokens 所致
        raise RuntimeError(
            f"任务 {task_id} 内容为空（finish_reason={finish_reason}），"
            f"如为 length 请调大 max_tokens")
    return content, finish_reason


def check_model(task_no, requested, echoed_models):
    """核对请求模型与接口实际使用模型，打印核对行，返回是否一致。

    echoed_models: [(来源说明, 回显的 model 原始字符串), ...]
    实际使用的模型以「最终结果回显」为准；提交回显一并核对、一并留痕。
    """
    target = normalize_model(requested)
    mismatches = []
    for source, echoed in echoed_models:
        if normalize_model(echoed) != target:
            mismatches.append((source, echoed))
    lines = [f"  [模型核对 {task_no}] 请求的模型 = {requested!r}"]
    for source, echoed in echoed_models:
        mark = "✅ 一致" if (source, echoed) not in mismatches else "❌ 不一致"
        lines.append(f"  {' ' * (len(f'[模型核对 {task_no}]'))}"
                     f" {source} = {echoed!r}  {mark}")
    print("\n".join(lines))
    for source, echoed in mismatches:
        print(f"  ⚠️  警报：{source}为 {echoed!r}，与请求的 {requested!r} 不一致！")
    return not mismatches


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        print("错误：请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）。",
              file=sys.stderr)
        return 2

    print(f"请求的模型（锁定版本）：{REQUESTED_MODEL}")
    print(f"待分类句子数：{len(SENTENCES)}")
    print("=" * 72)

    # 第一步：先把 3 个任务全部提交上去（服务端并行处理），再统一轮询。
    tasks = []
    for i, text in enumerate(SENTENCES, 1):
        task_id, submit_echo = submit_task(text, api_key)
        print(f"[任务 {i}] 已提交 task_id={task_id} 提交回显 model={submit_echo!r}")
        tasks.append((i, text, task_id, submit_echo))

    print("-" * 72)

    # 第二步：逐个轮询取结果，边取边做模型版本核对。
    audit_ok = True
    for i, text, task_id, submit_echo in tasks:
        result = poll_result(task_id, api_key)
        final_model = result.get("model")
        try:
            content, finish_reason = extract_content(result, task_id)
        except RuntimeError as exc:
            print(f"[任务 {i}] 分类失败：{exc}")
            audit_ok = audit_ok and check_model(
                i, REQUESTED_MODEL,
                [("提交接口回显", submit_echo), ("最终结果回显", final_model)])
            continue
        print(f"[任务 {i}] 句子：{text}")
        print(f"[任务 {i}] 分类结果：{content}（finish_reason={finish_reason}）")
        consistent = check_model(
            i, REQUESTED_MODEL,
            [("提交接口回显", submit_echo), ("最终结果回显", final_model)])
        audit_ok = audit_ok and consistent
        print("-" * 72)

    # 第三步：审计结论。不一致必须毫无歧义地报警，不能只埋在日志里。
    print("=" * 72)
    print("模型版本审计结论")
    print(f"  请求的模型       ：{REQUESTED_MODEL}")
    if audit_ok:
        print("  实际使用的模型   ：与请求一致（各任务明细见上方核对行）")
        print("  审计结果         ：✅ 通过，所有任务均运行在锁定的模型版本上")
        return 0
    print("  实际使用的模型   ：与请求不一致（各任务明细见上方核对行）")
    print("  审计结果         ：❌ 不通过")
    print()
    print("!" * 72)
    print("⚠️  审计警报：接口实际使用的模型与请求的模型不一致！")
    print(f"    审计要求锁定 {REQUESTED_MODEL!r}，但异步端点返回了不同的 model。")
    print("    智谱异步端点存在静默替换模型的行为（如 glm-4.6 -> glm-4.7），")
    print("    本次结果不满足版本锁定要求，请勿用于审计口径内的结论。")
    print("!" * 72)
    return 1


if __name__ == "__main__":
    sys.exit(main())
