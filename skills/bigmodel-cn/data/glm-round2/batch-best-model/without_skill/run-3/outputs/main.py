#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用智谱 BigModel 的 Batch API 对用户评论做情感分类（正面/负面/中性）。

流程：
1. 读取脚本同目录下的 comments.txt（每行一条评论）；
2. 生成符合 Batch 输入格式的 batch_requests.jsonl；
3. 上传该文件（purpose=batch），拿到 file id；
4. 用 file id 创建 batch 任务（Batch 价格为标准 API 的 50%）；
5. 把创建成功的 batch 任务 id 打印到 stdout（不等待任务跑完、不取结果）。

模型选用当前最强的旗舰模型 glm-5.3：分类质量优先，不降级到小模型。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
依赖：仅 requests。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-5.3"
# Batch 请求文件中每行的 url，以及创建 batch 时的 endpoint，都固定为这个值
CHAT_COMPLETIONS_PATH = "/v4/chat/completions"

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILE = SCRIPT_DIR / "comments.txt"
JSONL_FILE = SCRIPT_DIR / "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。判断给定评论的整体情感倾向，"
    "只输出「正面」「负面」「中性」三个标签之一，不要输出任何解释、标点或其他文字。\n"
    "判断标准：\n"
    "- 正面：表达满意、赞赏、推荐或正面体验；\n"
    "- 负面：表达不满、投诉、质量问题或负面体验；\n"
    "- 中性：客观陈述、褒贬不一、无明显倾向。\n"
    "示例：\n"
    "评论：发货很快，包装也很好 → 正面\n"
    "评论：客服态度差，问题没解决 → 负面\n"
    "评论：东西能用，没什么特别的 → 中性"
)


def log(msg: str) -> None:
    """进度信息打到 stderr，保证 stdout 只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def die(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def load_comments(path: Path) -> list:
    """读取评论文件，每行一条，去掉空行。"""
    if not path.exists():
        die(f"找不到评论文件：{path}")
    with open(path, "r", encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    if not comments:
        die(f"评论文件为空：{path}")
    return comments


def build_jsonl(comments: list, out_path: Path) -> None:
    """把每条评论写成一行 Batch 请求，格式为
    {"custom_id": ..., "method": "POST", "url": "/v4/chat/completions", "body": {...}}
    """
    with open(out_path, "w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                "custom_id": f"comment-{i}",
                "method": "POST",
                "url": CHAT_COMPLETIONS_PATH,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    # 分类任务要稳定可复现，用低温度
                    "temperature": 0.1,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")


def upload_file(api_key: str, path: Path) -> str:
    """上传 .jsonl 文件（purpose=batch），返回 file id。"""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=300,
        )
    if resp.status_code != 200:
        die(f"上传文件失败 [{resp.status_code}]：{resp.text}")
    return resp.json()["id"]


def create_batch(api_key: str, input_file_id: str) -> dict:
    """创建 batch 任务，返回 Batch 对象。"""
    resp = requests.post(
        f"{BASE_URL}/batches",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "input_file_id": input_file_id,
            "endpoint": CHAT_COMPLETIONS_PATH,
            # 保留服务端的输入文件（30 天后自动过期），便于排查分类结果
            "auto_delete_input_file": False,
            "metadata": {"task": "sentiment-classification"},
        },
        timeout=60,
    )
    if resp.status_code != 200:
        die(f"创建 batch 任务失败 [{resp.status_code}]：{resp.text}")
    return resp.json()


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("请先设置环境变量 ZHIPUAI_API_KEY")

    comments = load_comments(COMMENTS_FILE)
    log(f"从 {COMMENTS_FILE.name} 读取到 {len(comments)} 条评论")

    build_jsonl(comments, JSONL_FILE)
    log(f"已生成 Batch 请求文件 {JSONL_FILE.name}（模型：{MODEL}）")

    file_id = upload_file(api_key, JSONL_FILE)
    log(f"文件上传成功，file id：{file_id}")

    batch = create_batch(api_key, file_id)
    log(f"batch 任务创建成功，状态：{batch.get('status', 'n/a')}")

    # stdout 只输出 batch 任务 id，方便后续脚本接管（查询进度/取结果）
    print(batch["id"])


if __name__ == "__main__":
    main()
