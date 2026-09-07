#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类(正面/负面/中性)。

流程:读取同目录 comments.txt -> 构造 .jsonl 请求文件 -> 上传 -> 创建 batch 任务
-> 把 batch 任务 id 打印到 stdout(不等待任务完成)。

用法:
    export ZHIPUAI_API_KEY=sk-xxx
    python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# 分类质量优先,用当前旗舰模型
MODEL = "glm-5.3"
REQUESTS_FILENAME = "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是一个商品/服务用户评论的情感分类器。"
    "对给定的评论判断整体情感倾向,只输出下面三个标签之一:"
    "正面、负面、中性。不要输出任何其他内容、标点或解释。"
)


def log(msg: str) -> None:
    """进度信息走 stderr,保证 stdout 只有 batch 任务 id。"""
    print(msg, file=sys.stderr)


def find_comments_file() -> Path:
    """优先找脚本同目录的 comments.txt,找不到再退回当前工作目录。"""
    candidates = [
        Path(__file__).resolve().parent / "comments.txt",
        Path.cwd() / "comments.txt",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "找不到 comments.txt(已尝试脚本目录和当前目录): "
        + ", ".join(str(p) for p in candidates)
    )


def load_comments(path: Path) -> list:
    comments = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    comments = [c for c in comments if c]
    if not comments:
        raise ValueError(f"{path} 中没有有效评论(文件为空或全是空行)")
    return comments


def build_requests_file(comments, out_path: Path) -> Path:
    """按 Batch API 要求的 JSONL 格式逐行写入请求。"""
    with out_path.open("w", encoding="utf-8") as f:
        for idx, comment in enumerate(comments):
            request = {
                "custom_id": f"comment-{idx}",
                "method": "POST",
                "url": "/v4/chat/completions",
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
    return out_path


def check_response(resp: requests.Response, step: str) -> dict:
    """统一的响应检查,失败时把服务端错误打到 stderr。"""
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        log(f"{step} 失败: HTTP {resp.status_code} {resp.text}")
        raise
    return resp.json()


def upload_file(api_key: str, path: Path) -> str:
    resp = requests.post(
        f"{BASE_URL}/files",
        headers={"Authorization": f"Bearer {api_key}"},
        data={"purpose": "batch"},
        files={"file": (path.name, path.open("rb"), "application/json")},
        timeout=300,
    )
    data = check_response(resp, "上传请求文件")
    log(f"文件上传成功: {data['id']}")
    return data["id"]


def create_batch(api_key: str, file_id: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/batches",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "input_file_id": file_id,
            "endpoint": "/v4/chat/completions",
            "metadata": {"task": "sentiment-classification", "model": MODEL},
        },
        timeout=60,
    )
    data = check_response(resp, "创建 batch 任务")
    log(f"batch 任务已创建,状态: {data.get('status', 'unknown')}")
    return data["id"]


def main() -> int:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        log("错误: 请先设置环境变量 ZHIPUAI_API_KEY")
        return 1

    comments_path = find_comments_file()
    comments = load_comments(comments_path)
    log(f"从 {comments_path} 读取到 {len(comments)} 条评论,模型: {MODEL}")

    requests_path = build_requests_file(
        comments, comments_path.parent / REQUESTS_FILENAME
    )
    log(f"请求文件已生成: {requests_path}")

    file_id = upload_file(api_key, requests_path)
    batch_id = create_batch(api_key, file_id)

    # stdout 只输出 batch 任务 id,便于脚本间管道使用
    print(batch_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
