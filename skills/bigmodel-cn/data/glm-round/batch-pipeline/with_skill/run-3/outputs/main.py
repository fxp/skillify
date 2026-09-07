#!/usr/bin/env python3
"""用智谱 BigModel 的 Batch API 批量做用户评论情感分类（正面/负面/中性）。

Batch 价格为标准 API 的 50%。流程：读 comments.txt -> 构造 .jsonl 请求文件 ->
以 purpose=batch 上传 -> 创建 batch 任务 -> 把 batch 任务 id 打印到 stdout。
不等待任务跑完、不取结果。

用法：python3 main.py [comments.txt 路径]
API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
# 注意：Batch 只支持一份模型白名单（glm-5.3 等旗舰模型不在其中），且校验发生在
# 上传请求文件这一步就会报 1210。glm-4-air-250414 在官方 Batch 支持列表内，
# 改模型前先对照白名单核实。
MODEL = "glm-4-air-250414"
BATCH_ENDPOINT = "/v4/chat/completions"  # Batch 目前仅支持该端点

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断给定用户评论的情感倾向，"
    "只回答：正面、负面 或 中性 三个词中的一个，不要输出任何其他内容。"
)


def log(msg):
    print(msg, file=sys.stderr)


def find_comments_file():
    here = Path(__file__).resolve().parent
    candidates = [Path(sys.argv[1])] if len(sys.argv) > 1 else []
    candidates += [here / "comments.txt", Path.cwd() / "comments.txt"]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        "找不到 comments.txt：请把它放在脚本同目录（或当前目录），"
        "或用 `python3 main.py <comments.txt 路径>` 指定。"
    )


def build_request_file(comments_path, requests_path):
    """把每条评论写成一行 Batch 请求，返回请求条数。"""
    comments = [
        line.strip()
        for line in comments_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not comments:
        raise SystemExit(f"{comments_path} 里没有读到任何评论")

    with requests_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                # custom_id 用于把结果对回输入：全文件唯一，且最短 6 个字符
                # （"r1" 这类过短 id 会在文件上传阶段被 1210 拒绝）
                "custom_id": f"request-{i:03d}",
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"评论：{comment}"},
                    ],
                    "temperature": 0.1,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    return len(comments)


def die_on_error(resp, what):
    # 业务错误（如 1210 模型名/custom_id 非法）带 4xx 状态码，把响应体带出来方便排查
    if not resp.ok:
        raise SystemExit(f"{what}失败：HTTP {resp.status_code} {resp.text}")
    data = resp.json()
    if "error" in data:
        raise SystemExit(f"{what}失败：{data['error']}")
    return data


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量 ZHIPUAI_API_KEY（智谱开放平台 API Key）")
    headers = {"Authorization": f"Bearer {api_key}"}

    comments_path = find_comments_file()
    requests_path = Path.cwd() / "batch_requests.jsonl"
    count = build_request_file(comments_path, requests_path)
    log(f"已构造 {count} 条情感分类请求 -> {requests_path}")

    # 1) 上传请求文件；Batch 输入文件必须以 purpose=batch 上传，模型白名单在这一步校验
    with requests_path.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": (requests_path.name, f, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=120,
        )
    upload = die_on_error(resp, "上传请求文件")
    input_file_id = upload["id"]
    log(f"文件上传成功：{input_file_id}")

    # 2) 创建 batch 任务（completion_window 已废弃不再传；任务一般 24 小时内完成）
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=60,
    )
    batch = die_on_error(resp, "创建 batch 任务")
    log(f"batch 任务已创建：status={batch.get('status')}")

    print(batch["id"])


if __name__ == "__main__":
    main()
