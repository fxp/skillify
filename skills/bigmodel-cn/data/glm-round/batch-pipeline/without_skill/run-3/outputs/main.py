#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 的 Batch API 批量做用户评论的情感分类（正面/负面/中性）。

Batch 接口价格为常规调用的 50%。流程：
  1. 读取同目录下 comments.txt（每行一条评论），构造 batch_requests.jsonl
  2. 上传该文件（purpose=batch）
  3. 创建 batch 任务
  4. 把 batch 任务 id 打印到 stdout（不等待任务跑完、不取结果）

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
用法：python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-4-flash"
# 创建 batch 任务时的 endpoint 参数，目前仅支持 /v4/chat/completions
BATCH_ENDPOINT = "/v4/chat/completions"
SYSTEM_PROMPT = (
    "你是情感分类助手。请对给定的用户评论进行情感分类，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何其他内容。"
)


def log(msg):
    """进度信息走 stderr，保证 stdout 只有 batch 任务 id。"""
    print(msg, file=sys.stderr, flush=True)


def die(msg):
    print("错误：" + msg, file=sys.stderr, flush=True)
    sys.exit(1)


def find_comments_path():
    """在当前目录、脚本目录（及其上级）里找 comments.txt。"""
    script_dir = Path(__file__).resolve().parent
    for candidate in (
        Path.cwd() / "comments.txt",
        script_dir / "comments.txt",
        script_dir.parent / "comments.txt",
    ):
        if candidate.is_file():
            return candidate
    die("找不到 comments.txt（已尝试当前目录和脚本所在目录）")


def build_request_file(comments_path):
    """把每条评论变成一行 batch 请求，写入 batch_requests.jsonl。"""
    comments = [
        line.strip()
        for line in comments_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not comments:
        die("%s 里没有有效评论" % comments_path)

    out_path = comments_path.with_name("batch_requests.jsonl")
    with out_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                "custom_id": "comment-%05d" % i,
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    "temperature": 0.1,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    log("已生成 %d 条请求 -> %s" % (len(comments), out_path))
    return out_path


def parse_response(resp, action):
    """校验 HTTP 状态码并解析 JSON，失败则报错退出。"""
    if not resp.ok:
        die("%s 失败：HTTP %d %s" % (action, resp.status_code, resp.text))
    try:
        return resp.json()
    except ValueError:
        die("%s 失败：响应不是 JSON：%s" % (action, resp.text[:500]))


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")
    headers = {"Authorization": "Bearer " + api_key}

    # 1. 构造 .jsonl 请求文件并上传（purpose 必须为 batch）
    request_file = build_request_file(find_comments_path())
    with request_file.open("rb") as fh:
        upload_resp = requests.post(
            BASE_URL + "/files",
            headers=headers,
            data={"purpose": "batch"},
            files={"file": fh},
            timeout=120,
        )
    file_obj = parse_response(upload_resp, "上传请求文件")
    file_id = file_obj.get("id")
    if not file_id:
        die("上传响应里没有文件 id：%s" % file_obj)
    log("文件上传成功：%s" % file_id)

    # 2. 创建 batch 任务
    create_resp = requests.post(
        BASE_URL + "/batches",
        headers=dict(headers, **{"Content-Type": "application/json"}),
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": False,
        },
        timeout=60,
    )
    batch = parse_response(create_resp, "创建 batch 任务")
    batch_id = batch.get("id")
    if not batch_id:
        die("创建响应里没有任务 id：%s" % batch)
    log("batch 任务已创建，状态：%s" % batch.get("status", "unknown"))

    # 3. 只把任务 id 打到 stdout，结束（不轮询、不取结果）
    print(batch_id)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        die("网络请求异常：%s" % exc)
