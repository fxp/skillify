#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt -> 构造 .jsonl 批量请求文件 -> 上传文件
-> 创建 batch 任务 -> 把 batch 任务 id 打印到 stdout（不等待任务完成）。

运行前请设置环境变量 ZHIPUAI_API_KEY。仅依赖 requests。
"""

import json
import os
import sys
from pathlib import Path

import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
CHAT_ENDPOINT = "/v4/chat/completions"  # batch 文件里的 url 与创建任务时的 endpoint 均用此值
MODEL = "glm-5.3"  # 当前最强旗舰模型，质量优先（Batch 价格为标准 API 的 50%）

SCRIPT_DIR = Path(__file__).resolve().parent
BATCH_REQUESTS_FILE = SCRIPT_DIR / "batch_requests_sentiment.jsonl"

SYSTEM_PROMPT = (
    "你是一个用户评论情感分类器。阅读给定的用户评论，判断其整体情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。"
    "不要输出任何解释、标点或其他内容。"
    "既包含优点也包含抱怨的评论，按整体倾向更偏批评判为负面、更偏赞许判为正面；"
    "确实均衡或仅客观陈述的判为中性。"
)


def log(msg):
    """进度信息走 stderr，保证 stdout 只有最终的 batch id。"""
    print(msg, file=sys.stderr)


def load_comments():
    """在脚本目录、当前目录、脚本上级目录中寻找 comments.txt（每行一条评论）。"""
    candidates = [
        SCRIPT_DIR / "comments.txt",
        Path.cwd() / "comments.txt",
        SCRIPT_DIR.parent / "comments.txt",
    ]
    for path in candidates:
        if path.is_file():
            # utf-8-sig 顺便兼容带 BOM 的文件
            with path.open("r", encoding="utf-8-sig") as f:
                comments = [line.strip() for line in f if line.strip()]
            if not comments:
                sys.exit(f"错误：{path} 中没有有效评论。")
            return path, comments
    tried = "、".join(str(p) for p in candidates)
    sys.exit(f"错误：找不到 comments.txt（已尝试：{tried}）。")


def build_request_file(comments):
    """构造符合 BigModel Batch 规范的 .jsonl 请求文件，返回请求数。"""
    with BATCH_REQUESTS_FILE.open("w", encoding="utf-8") as f:
        for idx, comment in enumerate(comments, start=1):
            request = {
                "custom_id": f"comment-{idx:04d}",
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
    return len(comments)


def ensure_ok(resp, step):
    """非 2xx 或缺少预期字段时打印服务端错误并退出。"""
    if not (200 <= resp.status_code < 300):
        sys.exit(f"错误：{step} 失败，HTTP {resp.status_code}，响应：{resp.text}")
    try:
        return resp.json()
    except ValueError:
        sys.exit(f"错误：{step} 返回的不是 JSON，HTTP {resp.status_code}，响应：{resp.text}")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY。")
    headers = {"Authorization": f"Bearer {api_key}"}

    comments_path, comments = load_comments()
    count = build_request_file(comments)
    log(f"已读取 {comments_path}（{count} 条评论），请求文件：{BATCH_REQUESTS_FILE}")

    # 1) 上传批量请求文件（purpose 必须为 batch，格式 .jsonl）
    with BATCH_REQUESTS_FILE.open("rb") as f:
        upload = requests.post(
            f"{API_BASE}/files",
            headers=headers,
            data={"purpose": "batch"},
            files={"file": (BATCH_REQUESTS_FILE.name, f, "application/jsonl")},
            timeout=300,
        )
    upload_json = ensure_ok(upload, "上传请求文件")
    file_id = upload_json.get("id")
    if not file_id:
        sys.exit(f"错误：上传响应中没有文件 id：{json.dumps(upload_json, ensure_ascii=False)}")
    log(f"文件上传成功，file_id: {file_id}")

    # 2) 创建 batch 任务（endpoint 目前仅支持 /v4/chat/completions）
    create = requests.post(
        f"{API_BASE}/batches",
        headers=headers,
        json={
            "input_file_id": file_id,
            "endpoint": CHAT_ENDPOINT,
            "metadata": {
                "task": "sentiment-classification",
                "source_file": comments_path.name,
                "model": MODEL,
            },
        },
        timeout=60,
    )
    batch_json = ensure_ok(create, "创建 batch 任务")
    batch_id = batch_json.get("id")
    if not batch_id:
        sys.exit(f"错误：创建响应中没有 batch id：{json.dumps(batch_json, ensure_ascii=False)}")

    log(f"batch 任务创建成功，状态：{batch_json.get('status', 'unknown')}")
    print(batch_id)


if __name__ == "__main__":
    main()
