#!/usr/bin/env python3
"""用智谱 BigModel 的 Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取 comments.txt -> 构造 .jsonl 请求文件 -> 上传（purpose=batch）
-> 创建 batch 任务 -> 把 batch 任务 id 打印到 stdout。不等待任务跑完。

运行：python3 main.py（需要环境变量 ZHIPUAI_API_KEY，只需 requests）

模型选择说明（重要）：
Batch 接口有一份独立的模型白名单，平台旗舰 glm-5.3 / glm-5.2 都不在其中，
模型名不合法时会在"文件上传"这一步直接报 1210 模型名称错误。
白名单内目前最强的对话模型是 glm-5.1，质量优先因此选它。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.1"  # Batch 白名单内可用的最强模型；glm-5.3 不在白名单，走不了 Batch
ENDPOINT = "/v4/chat/completions"  # jsonl 每行的 url 必须与创建任务时的 endpoint 一致

SYSTEM_PROMPT = (
    "你是一个用户评论情感分类器。对给定的评论进行情感分类，"
    "输出且仅输出以下三个标签之一：正面、负面、中性。"
    "不要输出任何解释、标点、引号或其他多余文字。"
)


def find_comments_file():
    # 在脚本所在目录及其上级目录里找 comments.txt
    start = Path(__file__).resolve().parent
    for directory in [start, *start.parents]:
        candidate = directory / "comments.txt"
        if candidate.is_file():
            return candidate
    sys.exit(f"错误：找不到 comments.txt（已在 {start} 及其上级目录中查找）")


def load_comments(path):
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not comments:
        sys.exit(f"错误：{path} 中没有有效评论")
    return comments


def build_request_file(comments, out_path):
    with out_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, 1):
            request = {
                # custom_id 有未文档化的最短 6 字符限制，短了上传阶段直接报错，别改成 id-1 这类
                "custom_id": f"request-{i:06d}",
                "method": "POST",
                "url": ENDPOINT,
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
    return out_path


def api_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def check_response(resp, action):
    """智谱接口可能 HTTP 200 但 body 里带业务错误，两种情况都要检查。"""
    if not resp.ok:
        sys.exit(f"错误：{action}失败：HTTP {resp.status_code}，{resp.text}")
    try:
        body = resp.json()
    except ValueError:
        sys.exit(f"错误：{action}返回了非 JSON 内容：{resp.text[:500]}")
    if isinstance(body, dict) and body.get("error"):
        sys.exit(f"错误：{action}失败：{json.dumps(body['error'], ensure_ascii=False)}")
    return body


def upload_file(api_key, path):
    # purpose 必须是 batch，否则后续创建 batch 任务时无法引用
    with path.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=api_headers(api_key),
            files={"file": (path.name, f, "application/x-ndjson")},
            data={"purpose": "batch"},
            timeout=300,
        )
    body = check_response(resp, "上传请求文件")
    file_id = body["id"]
    print(f"请求文件已上传：{path.name} -> {file_id}", file=sys.stderr)
    return file_id


def create_batch(api_key, input_file_id):
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**api_headers(api_key), "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": ENDPOINT,
            "metadata": {"description": "用户评论情感分类"},
        },
        timeout=60,
    )
    body = check_response(resp, "创建 batch 任务")
    print(f"batch 任务创建成功，初始状态：{body.get('status')}", file=sys.stderr)
    return body["id"]


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY（https://bigmodel.cn/usercenter/proj-mgmt/apikeys）")

    comments_path = find_comments_file()
    comments = load_comments(comments_path)
    print(f"从 {comments_path} 读取到 {len(comments)} 条评论", file=sys.stderr)

    request_path = build_request_file(comments, Path(__file__).resolve().parent / "batch_requests.jsonl")
    print(f"已生成 batch 请求文件：{request_path}", file=sys.stderr)

    file_id = upload_file(api_key, request_path)
    batch_id = create_batch(api_key, file_id)

    # 唯一打印到 stdout 的内容，方便 shell 里直接捕获，例如：
    #   BATCH_ID=$(python3 main.py)
    print(batch_id)


if __name__ == "__main__":
    main()
