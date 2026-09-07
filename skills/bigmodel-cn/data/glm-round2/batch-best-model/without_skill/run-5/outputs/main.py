#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户评论情感分类（正面/负面/中性）—— 智谱 BigModel Batch 批量推理。

流程：
1. 读取脚本同目录（或当前目录）下的 comments.txt，每行一条评论；
2. 构造 batch 请求文件 batch_requests.jsonl，每行一个 chat/completions 请求；
3. 上传该文件（purpose="batch"）；
4. 创建 batch 任务，把任务 id 打印到 stdout（stdout 只输出 id，进度信息走 stderr）。

走 Batch 是因为价格只有实时接口的一半；模型用当前最强旗舰 glm-5.3。
API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import sys
from pathlib import Path

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-5.3"  # 当前最强旗舰模型
BATCH_ENDPOINT = "/v4/chat/completions"  # batch 目前仅支持该 endpoint
COMMENTS_FILENAME = "comments.txt"
REQUESTS_FILENAME = "batch_requests.jsonl"
UPLOAD_TIMEOUT = 120
CREATE_TIMEOUT = 60

SYSTEM_PROMPT = (
    "你是情感分类助手。请对用户给出的评论进行情感分类，"
    '只能输出"正面"、"负面"、"中性"三个词中的一个，不要输出任何其他内容。'
)


def log(msg):
    print(msg, file=sys.stderr)


def find_comments_path():
    """优先取脚本同目录下的 comments.txt，其次当前工作目录。"""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        candidate = base / COMMENTS_FILENAME
        if candidate.is_file():
            return candidate
    sys.exit("找不到 %s（脚本同目录或当前目录）" % COMMENTS_FILENAME)


def read_comments(path):
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    comments = [c for c in comments if c]
    if not comments:
        sys.exit("%s 里没有有效评论" % path)
    return comments


def build_request_lines(comments):
    """每行一个 batch 请求：custom_id 用于结果对回原评论。"""
    lines = []
    for idx, comment in enumerate(comments, start=1):
        lines.append(
            json.dumps(
                {
                    "custom_id": "comment-%05d" % idx,
                    "method": "POST",
                    "url": BATCH_ENDPOINT,
                    "body": {
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": comment},
                        ],
                    },
                },
                ensure_ascii=False,
            )
        )
    return lines


def write_requests_file(lines, path):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_response(resp, what):
    """返回正常响应的 JSON；出错时打印原因并以非零码退出。"""
    try:
        data = resp.json()
    except ValueError:
        sys.exit("%s失败：HTTP %d，响应不是 JSON：%s" % (what, resp.status_code, resp.text[:500]))
    if not resp.ok or "error" in data:
        sys.exit("%s失败：HTTP %d，%s" % (what, resp.status_code, data.get("error", data)))
    return data


def upload_requests_file(session, path):
    with path.open("rb") as fh:
        resp = session.post(
            "%s/files" % API_BASE,
            files={"file": (path.name, fh, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=UPLOAD_TIMEOUT,
        )
    return check_response(resp, "上传请求文件")["id"]


def create_batch(session, file_id):
    resp = session.post(
        "%s/batches" % API_BASE,
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "metadata": {"task": "sentiment-classification"},
        },
        timeout=CREATE_TIMEOUT,
    )
    return check_response(resp, "创建 batch 任务")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    comments_path = find_comments_path()
    comments = read_comments(comments_path)
    log("从 %s 读取到 %d 条评论，模型：%s" % (comments_path, len(comments), MODEL))

    requests_path = comments_path.parent / REQUESTS_FILENAME
    write_requests_file(build_request_lines(comments), requests_path)
    log("已生成请求文件 %s" % requests_path)

    session = requests.Session()
    session.headers["Authorization"] = "Bearer " + api_key

    try:
        file_id = upload_requests_file(session, requests_path)
        log("上传成功，file_id=%s" % file_id)

        batch = create_batch(session, file_id)
    except requests.RequestException as exc:
        sys.exit("请求 BigModel 接口失败：%s" % exc)

    log("batch 任务已创建，status=%s" % batch.get("status"))
    print(batch["id"])


if __name__ == "__main__":
    main()
