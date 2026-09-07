#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做评论情感分类（正面/负面/中性）。

流程：读 comments.txt -> 构造 .jsonl 请求文件 -> 上传（purpose=batch）
-> 创建 batch 任务 -> 把 batch 任务 id 打印到 stdout（不等待任务完成）。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
# 注意：Batch 只支持一份模型白名单（glm-5.3 等旗舰不在其中），
# glm-4-plus 在实测白名单内，校验发生在文件上传阶段。
MODEL = "glm-4-plus"
# jsonl 每行的 url 字段必须与创建 batch 时的 endpoint 一致
BATCH_ENDPOINT = "/v4/chat/completions"
COMMENTS_FILE = "comments.txt"
REQUESTS_FILE = "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是情感分类器。对给定的用户评论进行情感分类，"
    "只输出以下三个标签之一：正面、负面、中性。不要输出任何其他内容。"
)


def log(msg: str) -> None:
    """进度信息走 stderr，保证 stdout 只有 batch 任务 id，便于脚本解析。"""
    print(msg, file=sys.stderr)


def find_comments_file() -> Path:
    """优先找脚本同目录的 comments.txt，其次当前工作目录。"""
    candidates = [
        Path(__file__).resolve().parent / COMMENTS_FILE,
        Path.cwd() / COMMENTS_FILE,
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"找不到 {COMMENTS_FILE}，已尝试: {[str(p) for p in candidates]}"
    )


def build_requests_file(comments_file: Path) -> Path:
    """每条评论一行请求，custom_id 全局唯一且 >=6 字符（平台硬性要求）。"""
    out_path = Path.cwd() / REQUESTS_FILE
    lines = []
    with comments_file.open("r", encoding="utf-8") as f:
        for idx, raw in enumerate(f, start=1):
            comment = raw.strip()
            if not comment:
                continue
            lines.append(
                {
                    "custom_id": f"request-{idx:03d}",
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
            )
    if not lines:
        raise ValueError(f"{comments_file} 里没有有效评论")
    with out_path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    log(f"已生成请求文件 {out_path}，共 {len(lines)} 条")
    return out_path


def check_response(resp: requests.Response, step: str) -> dict:
    """HTTP 层与业务层错误都抛出，带上响应体方便排错。"""
    if not resp.ok:
        raise RuntimeError(f"{step} 失败: HTTP {resp.status_code} {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"{step} 失败: {data['error']}")
    return data


def upload_requests_file(path: Path, headers: dict) -> str:
    with path.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": f},
            data={"purpose": "batch"},
            timeout=120,
        )
    data = check_response(resp, "上传请求文件")
    file_id = data["id"]
    log(f"文件上传成功: {file_id}")
    return file_id


def create_batch(input_file_id: str, headers: dict) -> dict:
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "用户评论情感分类"},
        },
        timeout=60,
    )
    return check_response(resp, "创建 batch 任务")


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请先设置环境变量 ZHIPUAI_API_KEY")

    headers = {"Authorization": f"Bearer {api_key}"}

    comments_file = find_comments_file()
    requests_file = build_requests_file(comments_file)
    input_file_id = upload_requests_file(requests_file, headers)
    batch = create_batch(input_file_id, headers)

    log(f"batch 任务已创建，状态: {batch.get('status')}")
    # 只把任务 id 打到 stdout
    print(batch["id"])


if __name__ == "__main__":
    main()
