#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智谱开放平台「异步对话接口」批量情感分类 + 模型版本审计
=====================================================

流程（唯一第三方依赖：requests）：
  1. 批量提交：POST /paas/v4/async/chat/completions（异步接口不支持 stream），
     每句一个任务，提交后立即返回 {model, id, request_id, task_status}；
  2. 轮询结果：GET /paas/v4/async-result/{id}，直到 task_status 变为
     SUCCESS / FAIL 或超时（该接口与视频/图片生成共用，靠 task_status 区分）；
  3. 模型审计：把「我请求的 model」与「接口回显的 model」逐任务核对——
     提交回执和轮询结果各回显一次，两处都查。

为什么必须回读响应里的 model（本次审计的核心）：
  官方文档对响应 model 字段的定义是"此次调用使用的模型名称"，且异步端点
  实测会静默替换模型（2026-09 实测：请求 glm-4.6，异步端点实际跑 glm-4.7，
  同步端点不换）。所以"我传了 glm-4.6"不等于"任务真是 glm-4.6 跑的"，
  必须以响应回显为准核对，不一致立即报警。

比对规则：官方文档注明模型代码大小写不敏感（如请求 glm-5.3 会被回显成
  GLM-5.3），因此比对时忽略大小写；但两个原始值都原样打印，保留审计痕迹。
  回显字段缺失同样按不一致处理——审计上宁可误报不可漏报。

退出码：0 = 全部成功且模型一致；2 = 存在模型不一致（审计报警）；
        1 = 其他错误（缺 Key、网络失败、任务 FAIL 等）。

用法：
  export ZHIPUAI_API_KEY=你的Key
  python3 main.py
"""

import json
import os
import re
import sys
import time
import uuid

import requests

# ---------------------------------------------------------------- 基本配置

BASE_URL = "https://open.bigmodel.cn/api"
SUBMIT_URL = f"{BASE_URL}/paas/v4/async/chat/completions"
RESULT_URL = f"{BASE_URL}/paas/v4/async-result/{{task_id}}"

# 审计要求锁定的模型版本（只在此声明一次，全脚本以此为准）
REQUESTED_MODEL = "glm-4.6"

# 批量情感分类的三个句子
SENTENCES = [
    "这家店的招牌菜太好吃了，服务也特别热情，下次一定还来！",
    "快递拖了一个星期都没送到，联系客服只会打太极，太失望了。",
    "通知：今天下午三点在二楼会议室开项目复盘会，请准时参加。",
]

POLL_INTERVAL = 2.0   # 轮询间隔（官方建议 2-5 秒）
POLL_TIMEOUT = 300.0  # 单任务轮询总超时（秒）
HTTP_TIMEOUT = 30     # 单次 HTTP 请求超时（秒）

VALID_LABELS = ("positive", "negative", "neutral")
LABEL_ZH = {"positive": "正面", "negative": "负面", "neutral": "中性"}

# ---------------------------------------------------------------- 通用工具


def die(msg, code=1):
    print(f"\n[错误] {msg}", file=sys.stderr)
    sys.exit(code)


def load_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die("环境变量 ZHIPUAI_API_KEY 未设置。请先执行 export ZHIPUAI_API_KEY=<你的Key> 再运行。")
    return key


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def check_response(resp):
    """统一校验：HTTP 状态 + 平台业务错误体（{"error": {"code": ..., "message": ...}}）。"""
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"响应不是合法 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
    error = data.get("error") if isinstance(data, dict) else None
    if error:
        raise RuntimeError(f"平台返回错误 code={error.get('code')}：{error.get('message')}")
    resp.raise_for_status()
    return data


# ------------------------------------------------------- 提交 / 轮询 / 解析


def build_task_payload(sentence):
    request_id = uuid.uuid4().hex  # 6-64 字符，满足接口约束，审计追溯用
    return {
        "model": REQUESTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是情感分类器，对用户给出的句子做三分类。"
                    '只输出一个 JSON 对象：{"sentiment": "positive|negative|neutral"}，'
                    "不输出任何解释或其他文字。"
                ),
            },
            {"role": "user", "content": sentence},
        ],
        # 分类要可复现：do_sample=false 走贪心解码（temperature/top_p 被忽略）
        "do_sample": False,
        "max_tokens": 4096,
        # json_object 只是软约束，解析侧另有兜底（见 parse_sentiment）
        "response_format": {"type": "json_object"},
        "request_id": request_id,
    }


def submit_task(api_key, sentence):
    """提交一个异步任务，返回 (task_id, 提交回执回显的 model, request_id)。"""
    resp = requests.post(
        SUBMIT_URL,
        headers=auth_headers(api_key),
        json=build_task_payload(sentence),
        timeout=HTTP_TIMEOUT,
    )
    data = check_response(resp)
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError(f"异步提交未返回任务 id：{json.dumps(data, ensure_ascii=False)}")
    return task_id, data.get("model"), data.get("request_id")


def poll_result(api_key, task_id):
    """轮询通用异步结果接口，SUCCESS 时返回完整结果（含 model/choices/usage）。"""
    url = RESULT_URL.format(task_id=task_id)
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        resp = requests.get(url, headers=auth_headers(api_key), timeout=HTTP_TIMEOUT)
        data = check_response(resp)
        status = data.get("task_status")
        if status == "SUCCESS":
            return data
        if status == "FAIL":
            raise RuntimeError(f"异步任务 FAIL（task_id={task_id}）：{json.dumps(data, ensure_ascii=False)}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"轮询超时 >{POLL_TIMEOUT:.0f}s（task_id={task_id}），最后状态：{status}")
        time.sleep(POLL_INTERVAL)


def parse_sentiment(content):
    """
    解析模型输出里的情感标签。json_object 模式不是强约束（模型偶尔夹带文字），
    因此逐级降级：剥代码围栏后整体 json.loads → 正则截取 {...} 再解析 → 关键词匹配。
    """
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    candidates = [text]
    braces = re.search(r"\{.*\}", text, re.DOTALL)
    if braces:
        candidates.append(braces.group(0))

    for cand in candidates:
        try:
            label = str(json.loads(cand).get("sentiment", "")).strip().lower()
        except (ValueError, AttributeError):
            continue
        if label in VALID_LABELS:
            return label

    lowered = text.lower()
    for label in VALID_LABELS:
        if label in lowered:
            return label
    for label in VALID_LABELS:
        if LABEL_ZH[label] in text:
            return label
    return "unknown"


def same_model(requested, echoed):
    """模型代码大小写不敏感（官方文档），故忽略大小写比对；回显缺失视为不一致。"""
    if not echoed:
        return False
    return requested.strip().lower() == echoed.strip().lower()


# ---------------------------------------------------------------- 主流程


def main():
    key = load_api_key()
    total = len(SENTENCES)

    print("=" * 66)
    print("智谱异步对话接口 · 批量情感分类 · 模型版本审计")
    print(f"审计锁定的请求模型: {REQUESTED_MODEL}")
    print("=" * 66)

    # ---- 阶段 1：批量提交所有任务（异步的意义：提交即刻返回，不占住连接）----
    tasks = []
    for i, sentence in enumerate(SENTENCES, 1):
        try:
            task_id, submit_model, request_id = submit_task(key, sentence)
        except Exception as exc:
            die(f"任务 {i}/{total} 提交失败：{exc}")
        tasks.append(
            {
                "idx": i,
                "sentence": sentence,
                "task_id": task_id,
                "submit_model": submit_model,
                "request_id": request_id,
            }
        )
        print(f"[提交 {i}/{total}] task_id={task_id}  提交回执 model={submit_model!r}")

    # ---- 阶段 2 + 3：逐个轮询到终态，并对模型做审计核对 ----
    mismatches = []
    for t in tasks:
        print(f"\n----- 任务 {t['idx']}/{total}：{t['sentence']}")
        print(f"  我请求的模型       : {REQUESTED_MODEL}")
        print(f"  提交回执回显的模型 : {t['submit_model']!r}")

        try:
            result = poll_result(key, t["task_id"])
        except Exception as exc:
            die(f"任务 {t['idx']} 轮询失败：{exc}")

        actual_model = result.get("model")  # 官方定义：此次调用实际使用的模型名称
        print(f"  接口实际使用的模型 : {actual_model!r}（轮询结果回显）")

        choices = result.get("choices") or []
        if not choices:
            die(f"任务 {t['idx']} 已 SUCCESS 但响应中没有 choices：{json.dumps(result, ensure_ascii=False)}")
        message = choices[0].get("message") or {}
        finish_reason = choices[0].get("finish_reason")
        if finish_reason != "stop":
            print(f"  [警告] finish_reason={finish_reason!r}（非 stop），结果可能不完整")

        # ---- 模型审计：提交回执、轮询结果两处回显都必须与请求一致 ----
        ok_submit = same_model(REQUESTED_MODEL, t["submit_model"])
        ok_result = same_model(REQUESTED_MODEL, actual_model)
        if ok_submit and ok_result:
            print("  [审计] 模型核对一致（忽略大小写）✅")
        else:
            reasons = []
            if not ok_submit:
                reasons.append(f"提交回执 {t['submit_model']!r} != 请求 {REQUESTED_MODEL!r}")
            if not ok_result:
                reasons.append(f"实际模型 {actual_model!r} != 请求 {REQUESTED_MODEL!r}")
            print(f"  [审计报警] ❌ 模型不一致：{'；'.join(reasons)}")
            print(f"             本任务结果不能作为 {REQUESTED_MODEL} 的产出用于审计归档！")
            mismatches.append({"idx": t["idx"], "submit": t["submit_model"], "actual": actual_model})

        label = parse_sentiment(message.get("content"))
        usage = result.get("usage") or {}
        print(f"  分类结果           : {label}（{LABEL_ZH.get(label, '无法解析')}）")
        print(f"  模型原始输出       : {(message.get('content') or '').strip()!r}")
        print(f"  task_id={t['task_id']}  request_id={t['request_id']}  "
              f"total_tokens={usage.get('total_tokens')}")

    # ---- 审计汇总 ----
    print("\n" + "=" * 66)
    print("审计核对汇总")
    print(f"  请求模型（锁定）: {REQUESTED_MODEL}")
    for t in tasks:
        m = next((x for x in mismatches if x["idx"] == t["idx"]), None)
        verdict = "✅ 一致" if m is None else f"❌ 不一致（提交回执={m['submit']!r}，实际={m['actual']!r}）"
        print(f"  任务 {t['idx']}: {verdict}")
    print("=" * 66)

    if mismatches:
        print(f"❌ 审计报警：{len(mismatches)}/{total} 个任务的实际模型与请求的 {REQUESTED_MODEL!r} 不一致，")
        print("   本次结果不可用于锁定 glm-4.6 的审计归档，退出码置为 2。")
        print("   提示：异步端点已知会静默替换旧型号模型；如必须严格跑 glm-4.6，")
        print("   可改用同步端点 /paas/v4/chat/completions（实测不换模型）。")
        sys.exit(2)

    print(f"✅ 审计通过：{total}/{total} 个任务实际使用的模型均为 {REQUESTED_MODEL}。")


if __name__ == "__main__":
    main()
