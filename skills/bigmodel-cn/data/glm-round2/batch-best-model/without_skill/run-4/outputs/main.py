#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 的 Batch 批量推理接口对用户评论做情感分类（正面/负面/中性）。

流程：
  1. 读取同目录下 comments.txt（每行一条评论），构造 batch 请求文件 batch_requests.jsonl；
  2. 通过 Files API 上传该文件（purpose 必须为 batch）；
  3. 通过 Batch API 创建批量任务，把拿到的 batch 任务 id 打印到 stdout。

模型选用智谱当前最强的旗舰模型 GLM-5.3（Batch 价格为标准 API 的 50%）。
API Key 从环境变量 ZHIPUAI_API_KEY 读取，仅依赖 requests，可直接 python3 main.py 运行。
本脚本只负责创建任务，不等待任务完成、不拉取结果。
"""

import json
import os
import sys

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-5.3"  # 智谱最新旗舰模型：情感分类质量优先，Batch 价格为标准 API 的 50%
BATCH_ENDPOINT = "/v4/chat/completions"  # Batch 目前仅支持该 endpoint
COMMENTS_FILENAME = "comments.txt"
REQUESTS_FILENAME = "batch_requests.jsonl"
MAX_REQUESTS_PER_FILE = 50000  # 官方限制：单个 batch 文件最多 5 万条请求

SYSTEM_PROMPT = (
    "你是评论情感分类器。对用户给出的评论判断整体情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。"
    "不要输出标签以外的任何文字、标点或解释。"
)


def log(msg):
    print(f"[信息] {msg}", file=sys.stderr)


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def find_comments_path():
    """优先在脚本所在目录找 comments.txt，找不到再找当前工作目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for directory in (here, os.getcwd()):
        path = os.path.join(directory, COMMENTS_FILENAME)
        if os.path.isfile(path):
            return path
    return None


def load_comments(path):
    """读取评论，每行一条，去掉空行。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        return [line.strip() for line in f if line.strip()]


def build_requests_file(comments, path):
    """按 Batch API 要求的 jsonl 格式写请求文件：每行一个独立的 chat 请求。"""
    with open(path, "w", encoding="utf-8") as f:
        for idx, comment in enumerate(comments, start=1):
            request = {
                "custom_id": f"comment-{idx}",  # 结果文件按它把结果对回每条评论
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    "temperature": 0.1,  # 分类任务希望输出尽量稳定
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")


def parse_response_or_die(resp, action):
    """统一处理响应：非 2xx 或带 error 字段时打印服务端错误并退出，否则返回 JSON。"""
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not resp.ok:
        message = ""
        if isinstance(payload, dict):
            error = payload.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else str(error)
        die(f"{action}失败：HTTP {resp.status_code} {message or resp.text[:500]}")
    if isinstance(payload, dict) and payload.get("error"):
        die(f"{action}失败：{payload['error']}")
    if not isinstance(payload, dict):
        die(f"{action}失败：响应不是 JSON：{resp.text[:500]}")
    return payload


def upload_requests_file(api_key, path):
    """把 .jsonl 上传到 Files API（purpose=batch），返回 file_id。"""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(path), f, "text/plain")},
            data={"purpose": "batch"},
            timeout=300,
        )
    payload = parse_response_or_die(resp, "上传请求文件")
    file_id = payload.get("id")
    if not file_id:
        die(f"上传请求文件的响应里没有文件 id：{payload}")
    return file_id


def create_batch(api_key, file_id):
    """创建 batch 任务，返回 batch id。"""
    resp = requests.post(
        f"{API_BASE}/batches",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": False,  # 保留输入文件便于复查
            "metadata": {"task": "sentiment-classification"},
        },
        timeout=60,
    )
    payload = parse_response_or_die(resp, "创建 batch 任务")
    batch_id = payload.get("id")
    if not batch_id:
        die(f"创建 batch 任务的响应里没有任务 id：{payload}")
    return batch_id


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")

    comments_path = find_comments_path()
    if comments_path is None:
        die(f"找不到 {COMMENTS_FILENAME}（已在脚本目录和当前目录查找）")

    comments = load_comments(comments_path)
    if not comments:
        die(f"{comments_path} 里没有非空评论")
    if len(comments) > MAX_REQUESTS_PER_FILE:
        die(f"评论共 {len(comments)} 条，超过单个 batch 文件 {MAX_REQUESTS_PER_FILE} 条的上限，请分批运行")
    log(f"从 {comments_path} 读取到 {len(comments)} 条评论")

    requests_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), REQUESTS_FILENAME
    )
    build_requests_file(comments, requests_path)
    log(f"已生成 batch 请求文件 {requests_path}（模型 {MODEL}）")

    file_id = upload_requests_file(api_key, requests_path)
    log(f"请求文件上传成功：file_id={file_id}")

    batch_id = create_batch(api_key, file_id)
    log("batch 任务创建成功")

    # 按约定：stdout 只输出 batch 任务 id，其余进度信息都走 stderr
    print(batch_id)


if __name__ == "__main__":
    main()
