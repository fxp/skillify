#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt（每行一条评论）-> 构造 batch_requests.jsonl
-> 上传文件（purpose=batch）-> 创建 batch 任务 -> 把任务 id 打印到 stdout。
不需要等待任务完成；结果文件之后可通过
GET /api/paas/v4/batches/{id} 查询状态，再用 output_file_id 下载。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# Batch 支持的模型均可，glm-4-flash 走 Batch 免费且够用于简单分类，
# 可按需换成 glm-4-air / glm-4-plus 等（注意：单个 batch 文件只能含一个模型的请求）。
MODEL = "glm-4-flash"
CHAT_ENDPOINT = "/v4/chat/completions"  # batch 接口约定的 endpoint / url 写法

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
REQUESTS_FILE = SCRIPT_DIR / "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断用户评论的情感倾向，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)


def check_response(resp, what):
    """API 返回非 2xx 时直接报错退出，带上响应体方便排查。"""
    if resp.status_code < 200 or resp.status_code >= 300:
        sys.exit(f"{what} 失败: HTTP {resp.status_code} {resp.text}")


def load_comments(path):
    if not path.is_file():
        sys.exit(f"找不到评论文件: {path}")
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not comments:
        sys.exit(f"评论文件为空: {path}")
    return comments


def build_request_file(comments, path):
    """每行一个请求；custom_id 用行号，之后可把结果按 id 回填到对应评论。"""
    with path.open("w", encoding="utf-8") as f:
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
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")


def upload_request_file(api_key, path):
    """上传 .jsonl 文件，purpose 必须是 batch，返回文件 id。"""
    with path.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=60,
        )
    check_response(resp, "上传文件")
    return resp.json()["id"]


def create_batch(api_key, file_id):
    """创建 batch 任务，返回任务详情 dict。"""
    resp = requests.post(
        f"{BASE_URL}/batches",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "input_file_id": file_id,
            "endpoint": CHAT_ENDPOINT,
            "metadata": {"description": "用户评论情感分类：正面/负面/中性"},
        },
        timeout=60,
    )
    check_response(resp, "创建 batch 任务")
    return resp.json()


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    comments = load_comments(COMMENTS_FILE)
    build_request_file(comments, REQUESTS_FILE)
    print(f"已生成请求文件 {REQUESTS_FILE}（{len(comments)} 条评论）", file=sys.stderr)

    file_id = upload_request_file(api_key, REQUESTS_FILE)
    print(f"文件上传成功: {file_id}", file=sys.stderr)

    batch = create_batch(api_key, file_id)
    print(f"batch 任务已创建, 初始状态: {batch.get('status')}", file=sys.stderr)

    # 任务 id 单独打到 stdout，方便 `python3 main.py | xargs ...` 之类的取用
    print(batch["id"])


if __name__ == "__main__":
    main()
