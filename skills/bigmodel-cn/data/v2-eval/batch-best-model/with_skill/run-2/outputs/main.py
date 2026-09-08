#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取脚本同目录的 comments.txt（每行一条评论）
  → 构造 batch_requests.jsonl 请求文件
  → 上传（purpose=batch）
  → 创建 batch 任务
  → 把 batch 任务 id 打印到 stdout（进度信息走 stderr，stdout 只有任务 id，方便管道取值）。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
SCRIPT_DIR = Path(__file__).resolve().parent

# 模型选择：Batch 支持的不是平台全部模型，而是一份独立白名单，且校验发生在
# 文件上传阶段——平台旗舰 glm-5.3 / glm-5.2 不在白名单内，上传即报 1210「模型名称错误」。
# 白名单内质量最强的是 glm-5.1（5.x 旗舰系列，对齐 Claude Opus 4.6 档位），
# 因此在「质量优先 + 必须能跑通 Batch」的约束下选 glm-5.1，而不是退到 glm-4 系或 flash 档。
MODEL = "glm-5.1"

SYSTEM_PROMPT = (
    "你是一个情感分类器。对给定的用户评论进行情感分类，"
    "类别只有三种：正面、负面、中性。"
    "判定标准：表达满意、赞扬、推荐倾向的为正面；表达不满、抱怨、失望的为负面；"
    "客观陈述、无明显褒贬或褒贬相抵的为中性。"
    "只输出「正面」「负面」「中性」这三个词中的一个，不要输出任何解释、标点或其他内容。"
)


def log(msg):
    """进度信息打到 stderr，保持 stdout 干净、只输出 batch 任务 id。"""
    print(msg, file=sys.stderr)


def check_response(resp, action):
    """平台业务错误不一定伴随 4xx/5xx，HTTP 状态码和响应体都要检查。"""
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"{action} 失败：HTTP {resp.status_code}，非 JSON 响应：{resp.text[:500]}")
    if not resp.ok or "error" in data:
        raise RuntimeError(
            f"{action} 失败：HTTP {resp.status_code}，响应：{json.dumps(data, ensure_ascii=False)[:1000]}"
        )
    return data


def read_comments(path):
    if not path.is_file():
        raise FileNotFoundError(f"找不到评论文件：{path}（每行一条评论，utf-8 编码）")
    with open(path, encoding="utf-8") as f:
        comments = [line.strip() for line in f if line.strip()]
    if not comments:
        raise ValueError(f"评论文件是空的：{path}")
    return comments


def build_request_lines(comments):
    lines = []
    for i, comment in enumerate(comments, start=1):
        # custom_id 必须唯一，且有未文档化的最短 6 字符限制（"r1" 这类短 id
        # 会在上传阶段直接报错），"request-000001" 这种格式稳妥且可读。
        lines.append(
            {
                "custom_id": f"request-{i:06d}",
                "method": "POST",
                "url": "/v4/chat/completions",
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"评论：{comment}"},
                    ],
                    # 分类任务要输出稳定、可复现，温度压低
                    "temperature": 0.1,
                },
            }
        )
    return lines


def write_jsonl(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量 ZHIPUAI_API_KEY")

    comments_path = SCRIPT_DIR / "comments.txt"
    comments = read_comments(comments_path)
    log(f"读取到 {len(comments)} 条评论")

    jsonl_path = SCRIPT_DIR / "batch_requests.jsonl"
    write_jsonl(build_request_lines(comments), jsonl_path)
    log(f"已生成请求文件：{jsonl_path}")

    headers = {"Authorization": f"Bearer {api_key}"}

    # 1. 上传请求文件（purpose 必须是 batch；模型白名单校验就发生在这一步）
    with open(jsonl_path, "rb") as f:
        upload_resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=headers,
            files={"file": f},
            data={"purpose": "batch"},
            timeout=120,
        )
    upload = check_response(upload_resp, "上传请求文件")
    input_file_id = upload["id"]
    log(f"文件上传成功：{input_file_id}")

    # 2. 创建 batch 任务
    create_resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            # 保留原始输入文件，便于任务校验失败时排查或重新提交
            "auto_delete_input_file": False,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=60,
    )
    batch = check_response(create_resp, "创建 batch 任务")
    batch_id = batch["id"]
    log(f"batch 任务创建成功，状态：{batch.get('status', 'unknown')}")

    # 任务 id 单独打到 stdout
    print(batch_id)


if __name__ == "__main__":
    main()
