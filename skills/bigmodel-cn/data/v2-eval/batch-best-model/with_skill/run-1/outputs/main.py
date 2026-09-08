#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt -> 构造 .jsonl 请求文件 -> 上传（purpose=batch）
-> 创建 batch 任务 -> 打印 batch 任务 id。不等待任务完成。

模型说明：Batch 不支持平台全部模型（独立白名单，旗舰 glm-5.3 不在其中，
上传阶段就会报 1210 模型名称错误），白名单内质量最强的是 glm-5.1，
因此本脚本用 glm-5.1。Batch 价格为标准 API 的 50%。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
注意：调用 Batch API 前账号须完成实名认证。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.1"  # Batch 白名单内可用的最强模型（glm-5.3 不支持 Batch）
ENDPOINT = "/v4/chat/completions"  # Batch 目前仅支持这一种 endpoint

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
REQUESTS_FILE = SCRIPT_DIR / "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。对给定的评论判断整体情感倾向，"
    "只输出一个词作为答案：正面、负面 或 中性。"
    "褒贬明显以贬为主判负面、以褒为主判正面；褒贬参半或明显中性表述判中性。"
    "除这个词外不要输出任何其他内容。"
)


def die(step: str, resp: requests.Response) -> None:
    """带上下文退出，响应体里通常有业务错误码（如 1210 模型名称错误）。"""
    sys.exit(f"{step}失败 HTTP {resp.status_code}: {resp.text}")


def build_request_file() -> int:
    """把每条评论写成一行 batch 请求，返回请求条数。"""
    comments = [
        line.strip()
        for line in COMMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not comments:
        sys.exit(f"错误：{COMMENTS_FILE} 中没有读到任何评论")

    with REQUESTS_FILE.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                # custom_id 有未文档化的最短 6 字符限制，过短会在上传时报错，用 request-001 格式
                "custom_id": f"request-{i:03d}",
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
    return len(comments)


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    n = build_request_file()
    print(f"已生成 {REQUESTS_FILE.name}（{n} 条请求，模型 {MODEL}）")

    # 1. 上传请求文件（Batch 用的文件 purpose 必须是 batch，格式 .jsonl）
    with REQUESTS_FILE.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": ("batch_requests.jsonl", f)},
            data={"purpose": "batch"},
            timeout=300,
        )
    if resp.status_code != 200:
        die("上传请求文件", resp)
    file_obj = resp.json()
    if "id" not in file_obj:
        sys.exit(f"上传请求文件失败：{file_obj}")
    input_file_id = file_obj["id"]
    print(f"请求文件上传成功: {input_file_id}")

    # 2. 创建 batch 任务
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": ENDPOINT,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=60,
    )
    if resp.status_code != 200:
        die("创建 batch 任务", resp)
    batch = resp.json()
    if "id" not in batch:
        sys.exit(f"创建 batch 任务失败：{batch}")
    print(f"batch 任务创建成功，状态: {batch.get('status', 'unknown')}")
    print(batch["id"])


if __name__ == "__main__":
    main()
