#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱（bigmodel.cn）Batch API 批量做用户评论情感分类。

用法：
    export ZHIPUAI_API_KEY=<你的标准 API Key>
    python3 main.py

流程：读取脚本同目录 comments.txt（每行一条评论）-> 构造 batch 请求 jsonl
-> 上传（purpose=batch）-> 创建 batch 任务 -> 打印 batch 任务 id（不等待跑完）。

关于模型：Batch API 有一份独立的模型白名单，在**上传 jsonl 阶段**校验，
旗舰 glm-5.3 不在白名单内（会报业务码 1210「模型名称错误」）。因此脚本
先用 glm-5.3 尝试上传，一旦被拒，自动改用白名单内质量最强的 glm-5.1
重建 jsonl 重试，并把调整原因打印出来。
"""

import json
import os
import sys
import time

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMMENTS_FILE = os.path.join(SCRIPT_DIR, "comments.txt")
JSONL_FILE = os.path.join(SCRIPT_DIR, "batch_requests.jsonl")

PREFERRED_MODEL = "glm-5.3"   # 首选：平台旗舰（用户指定）
FALLBACK_MODEL = "glm-5.1"    # Batch 白名单内质量最强的模型
BATCH_ENDPOINT = "/v4/chat/completions"  # Batch 目前仅支持该端点
MODEL_CANDIDATES = [PREFERRED_MODEL, FALLBACK_MODEL]

SYSTEM_PROMPT = (
    "你是情感分类器。对给到的用户评论做情感分类，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)
# 分类答案只有几个 token，但思考链计入 max_tokens，预算给足，
# 避免 finish_reason=length / 正文为空（坑：思考 token 占用输出预算）
MAX_TOKENS = 2048
TEMPERATURE = 0.1


class ApiError(Exception):
    """智谱接口返回的业务/HTTP 错误。"""

    def __init__(self, status, code, message):
        self.status = status
        self.code = str(code) if code is not None else ""
        self.message = str(message) if message else ""
        super().__init__(f"HTTP {status}, code={self.code}, message={self.message}")


def extract_api_error(resp):
    """从响应里解析业务错误码（兼容 error.code 与顶层 code 两种形态）。"""
    try:
        body = resp.json()
    except ValueError:
        body = {}
    code, message = None, None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code, message = err.get("code"), err.get("message")
        if code is None:
            code, message = body.get("code"), body.get("message")
    if not message:
        message = resp.text[:300]
    return ApiError(resp.status_code, code, message)


def is_model_rejected(err):
    """上传阶段的 1210「模型名称错误」= 模型不在 Batch 白名单内。"""
    return err.code == "1210" and "模型" in err.message


def with_retry(fn, what="请求", tries=3):
    """对网络抖动 / 429 / 5xx 做少量重试；4xx 业务错误不重试，直接返回。"""
    last = None
    for attempt in range(1, tries + 1):
        try:
            resp = fn()
        except requests.RequestException as exc:
            last = exc
        else:
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if attempt < tries:
            print(f"  {what}失败（{last}），{2 * attempt}s 后重试…")
            time.sleep(2 * attempt)
    raise RuntimeError(f"{what}连续 {tries} 次失败：{last}")


def read_comments(path):
    if not os.path.exists(path):
        sys.exit(f"找不到评论文件：{path}")
    with open(path, "r", encoding="utf-8-sig") as f:
        return [line.strip() for line in f if line.strip()]


def build_requests(model, comments):
    """每行一个独立的 chat/completions 请求；custom_id 最短 6 字符。"""
    return [
        {
            "custom_id": f"request-{i:04d}",
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": comment},
                ],
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
            },
        }
        for i, comment in enumerate(comments, start=1)
    ]


def write_jsonl(path, requests_):
    with open(path, "w", encoding="utf-8") as f:
        for req in requests_:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")


def upload_batch_file(api_key, path):
    """上传 jsonl（purpose=batch）。白名单校验发生在这一步。"""

    def _do():
        # 每次重试都重新打开文件，避免重放已消费的文件句柄
        with open(path, "rb") as f:
            return requests.post(
                f"{BASE_URL}/paas/v4/files",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(path), f, "application/jsonl")},
                data={"purpose": "batch"},
                timeout=120,
            )

    resp = with_retry(_do, what="上传请求文件")
    body = resp.json()
    if resp.status_code != 200 or (isinstance(body, dict) and body.get("error")):
        raise extract_api_error(resp)
    file_id = body.get("id")
    if not file_id:
        raise RuntimeError(f"上传返回里没有文件 id：{resp.text[:300]}")
    return file_id


def create_batch(api_key, input_file_id, model):
    def _do():
        return requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input_file_id": input_file_id,
                "endpoint": BATCH_ENDPOINT,
                "auto_delete_input_file": True,
                "metadata": {"description": "用户评论情感分类", "model": model},
            },
            timeout=60,
        )

    resp = with_retry(_do, what="创建 batch 任务")
    body = resp.json()
    if resp.status_code != 200 or (isinstance(body, dict) and body.get("error")):
        raise extract_api_error(resp)
    return body


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY（标准 API Key）")

    comments = read_comments(COMMENTS_FILE)
    if not comments:
        sys.exit(f"没有读到任何评论，请检查 {COMMENTS_FILE}（每行一条）")
    print(f"从 {COMMENTS_FILE} 读到 {len(comments)} 条评论")

    # 依次尝试候选模型：首选旗舰；被 Batch 白名单拒绝则降级
    model_used = None
    input_file_id = None
    for model in MODEL_CANDIDATES:
        write_jsonl(JSONL_FILE, build_requests(model, comments))
        print(f"正在上传 batch 请求文件（模型 {model}）…")
        try:
            input_file_id = upload_batch_file(api_key, JSONL_FILE)
        except ApiError as err:
            if is_model_rejected(err) and model != MODEL_CANDIDATES[-1]:
                print()
                print(f"⚠️  服务端拒绝了 {model} 的请求文件：")
                print(f"    错误码 {err.code}：{err.message}")
                print(f"    原因：Batch API 只支持一份独立的模型白名单，且在文件上传")
                print(f"    阶段就校验；旗舰 {PREFERRED_MODEL} 不在白名单内，重试同样的")
                print(f"    模型没有意义。自动改用白名单内质量最强的 {FALLBACK_MODEL}。")
                print()
                continue
            raise
        model_used = model
        break

    if not input_file_id:
        sys.exit("上传 batch 请求文件失败，任务未创建")

    print(f"上传成功（文件 id：{input_file_id}），正在创建 batch 任务…")
    batch = create_batch(api_key, input_file_id, model_used)

    batch_id = batch.get("id")
    if not batch_id:
        sys.exit(f"创建 batch 失败：{json.dumps(batch, ensure_ascii=False)[:300]}")

    # 计数字段是嵌套的 request_counts.{total,completed,failed}，不是顶层字段
    counts = batch.get("request_counts") or {}

    print()
    print("=" * 60)
    print("✅ Batch 任务创建成功（不等待跑完）")
    print(f"   batch 任务 id : {batch_id}")
    print(f"   实际使用模型  : {model_used}")
    print(f"   状态          : {batch.get('status')}")
    print(f"   请求数        : {counts.get('total', len(comments))}")
    print("=" * 60)
    if model_used != PREFERRED_MODEL:
        print(f"注：首选 {PREFERRED_MODEL} 被 Batch 白名单拒绝，已降级为 {model_used}")
        print(f"    （白名单内质量最优的选择）。完整白名单见上面的服务端报错原文。")
    print("任务通常 24 小时内完成，稍后可用下面命令查询进度：")
    print(f'  curl -H "Authorization: Bearer $ZHIPUAI_API_KEY" \\')
    print(f"    {BASE_URL}/paas/v4/batches/{batch_id}")


if __name__ == "__main__":
    try:
        main()
    except ApiError as err:
        sys.exit(f"调用智谱 API 失败：{err}")
