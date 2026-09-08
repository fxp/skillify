#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量对评论做情感分类（正面/负面/中性）。

流程：读同目录 comments.txt -> 构造 batch_requests.jsonl -> 上传（purpose=batch）
-> 创建 batch 任务 -> 把 batch 任务 id 打印到 stdout。不等待任务完成。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
UPLOAD_URL = f"{BASE_URL}/paas/v4/files"
BATCHES_URL = f"{BASE_URL}/paas/v4/batches"
TIMEOUT = 60

# Batch 有一份独立于平台整体的模型白名单：旗舰 glm-5.3 / glm-5.2 都不在名单里，
# .jsonl 里写了它们会在文件上传阶段直接报 1210「模型名称错误」。
# 截至 2026-09，白名单内质量最强的是 glm-5.1（200K 上下文），质量优先就选它。
MODEL = "glm-5.1"

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
REQUESTS_FILE = SCRIPT_DIR / "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是情感分类助手。对用户给出的评论做情感分类，"
    "标签只能是「正面」「负面」「中性」三选一。"
    "只输出标签本身，不要输出任何解释、标点或其他文字。"
)


def log(msg):
    """进度信息走 stderr，保证 stdout 里只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def die(msg):
    sys.exit(f"错误：{msg}")


def load_api_key():
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        die("环境变量 ZHIPUAI_API_KEY 未设置，请先 export ZHIPUAI_API_KEY=<你的 Key>")
    return key


def load_comments(path):
    if not path.exists():
        die(f"找不到评论文件 {path}")
    comments = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not comments:
        die(f"评论文件 {path} 里没有有效内容")
    return comments


def build_requests_file(comments, path):
    """每行一个独立的 chat/completions 请求。

    注意：custom_id 有未文档化的 6 字符下限，短 id 会在上传阶段被拒，
    因此用 request-0001 这种格式；每行的 url 必须与 batch 任务的 endpoint 一致。
    """
    with path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            row = {
                "custom_id": f"request-{i:04d}",
                "method": "POST",
                "url": "/v4/chat/completions",
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"评论：{comment}"},
                    ],
                    "temperature": 0.1,
                    # 分类任务不需要深度思考：省 token，也避免思考预算吃掉 max_tokens 导致空输出。
                    # glm-5.1 支持显式关闭（glm-5.3 在标准端点不支持，勿照搬到别的模型）。
                    "thinking": {"type": "disabled"},
                    "max_tokens": 512,
                },
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def parse_payload(resp, what):
    """统一拦截 HTTP 错误和「HTTP 200 但 body 里带 error」两种失败。"""
    try:
        payload = resp.json()
    except ValueError:
        die(f"{what} 失败：返回不是 JSON（HTTP {resp.status_code}）：{resp.text[:300]}")
    if not resp.ok:
        die(f"{what} 失败（HTTP {resp.status_code}）：{payload}")
    if payload.get("error"):
        die(f"{what} 失败（业务错误）：{payload['error']}")
    return payload


def main():
    auth_headers = {"Authorization": f"Bearer {load_api_key()}"}

    comments = load_comments(COMMENTS_FILE)
    log(f"从 {COMMENTS_FILE.name} 读到 {len(comments)} 条评论")

    build_requests_file(comments, REQUESTS_FILE)
    log(f"已构造批量请求文件 {REQUESTS_FILE.name}（模型 {MODEL}）")

    # 1) 上传请求文件：purpose 必须是 batch；模型白名单校验就发生在这一步
    with REQUESTS_FILE.open("rb") as fh:
        upload_resp = requests.post(
            UPLOAD_URL,
            headers=auth_headers,
            files={"file": fh},
            data={"purpose": "batch"},
            timeout=TIMEOUT,
        )
    input_file_id = parse_payload(upload_resp, "上传请求文件").get("id")
    if not input_file_id:
        die(f"上传请求文件失败：响应里没有文件 id：{upload_resp.json()}")
    log(f"上传成功，input_file_id={input_file_id}")

    # 2) 创建 batch 任务，引用上传得到的文件 id
    create_resp = requests.post(
        BATCHES_URL,
        headers={**auth_headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "metadata": {"description": "comments sentiment classification"},
        },
        timeout=TIMEOUT,
    )
    batch = parse_payload(create_resp, "创建 batch 任务")
    if not batch.get("id"):
        die(f"创建 batch 任务失败：响应里没有任务 id：{batch}")
    log(f"batch 任务创建成功，状态：{batch.get('status', 'unknown')}")

    # stdout 只输出 batch 任务 id，方便被其他脚本管道消费
    print(batch["id"])


if __name__ == "__main__":
    main()
