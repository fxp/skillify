#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 的 Batch 批量推理接口对用户评论做情感分类（正面/负面/中性）。

Batch 价格为标准接口的一半。流程：
1. 读取同目录 comments.txt（每行一条评论）；
2. 构造 Batch 要求的 .jsonl 请求文件；
3. 上传文件（purpose=batch）；
4. 创建 batch 任务；
5. 把拿到的 batch 任务 id 打印到 stdout（进度信息走 stderr，不污染 stdout）。

用法：
    export ZHIPUAI_API_KEY=你的APIKey
    python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
CHAT_ENDPOINT = "/v4/chat/completions"  # jsonl 每行的 url 和创建任务时的 endpoint 都用这个值
MODEL = "glm-4-flash"  # Batch 支持的模型之一，目前免费
SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
REQUESTS_FILE = SCRIPT_DIR / "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断给定用户评论的情感倾向，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)

UPLOAD_TIMEOUT = 120
CREATE_TIMEOUT = 60


def die(msg):
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def load_comments(path):
    if not path.is_file():
        die(f"找不到评论文件：{path}")
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    comments = [c for c in comments if c]
    if not comments:
        die(f"评论文件里没有内容：{path}")
    return comments


def build_request_file(comments, out_path):
    """每条评论一行，按 Batch 接口要求的格式写 .jsonl 请求文件。"""
    with out_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                "custom_id": f"comment-{i}",
                "method": "POST",
                "url": CHAT_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 16,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    return out_path


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def upload_file(api_key, path):
    """上传 .jsonl 文件（purpose=batch），返回文件 id。"""
    try:
        with path.open("rb") as f:
            resp = requests.post(
                f"{BASE_URL}/files",
                headers=auth_headers(api_key),
                data={"purpose": "batch"},
                files={"file": (path.name, f, "application/jsonl")},
                timeout=UPLOAD_TIMEOUT,
            )
    except requests.RequestException as exc:
        die(f"上传文件请求失败：{exc}")
    if not resp.ok:
        die(f"上传文件失败 HTTP {resp.status_code}：{resp.text}")
    file_id = resp.json().get("id")
    if not file_id:
        die(f"上传文件的响应里没有 id：{resp.text}")
    return file_id


def create_batch(api_key, input_file_id):
    """用上传后的文件 id 创建 batch 任务，返回 batch 任务 id。"""
    try:
        resp = requests.post(
            f"{BASE_URL}/batches",
            headers={**auth_headers(api_key), "Content-Type": "application/json"},
            json={"input_file_id": input_file_id, "endpoint": CHAT_ENDPOINT},
            timeout=CREATE_TIMEOUT,
        )
    except requests.RequestException as exc:
        die(f"创建 batch 任务请求失败：{exc}")
    if not resp.ok:
        die(f"创建 batch 任务失败 HTTP {resp.status_code}：{resp.text}")
    batch_id = resp.json().get("id")
    if not batch_id:
        die(f"创建 batch 任务的响应里没有 id：{resp.text}")
    return batch_id


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")

    comments = load_comments(COMMENTS_FILE)
    print(f"[info] 读到 {len(comments)} 条评论", file=sys.stderr)

    requests_path = build_request_file(comments, REQUESTS_FILE)
    print(f"[info] 已生成请求文件 {requests_path}", file=sys.stderr)

    file_id = upload_file(api_key, requests_path)
    print(f"[info] 上传成功 file_id={file_id}", file=sys.stderr)

    batch_id = create_batch(api_key, file_id)
    print(f"[info] batch 任务创建成功", file=sys.stderr)
    print(batch_id)


if __name__ == "__main__":
    main()
