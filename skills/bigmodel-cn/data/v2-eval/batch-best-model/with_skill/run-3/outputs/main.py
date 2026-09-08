#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读 comments.txt → 构造 .jsonl 请求文件 → 上传（purpose=batch）
→ 创建 batch 任务 → 把 batch 任务 id 打印到 stdout（不等待任务完成）。

模型选择说明（重要）：
Batch 接口只支持一份独立的模型白名单，旗舰 glm-5.3 / glm-5.2 都不在其中——
把白名单外的模型写进 .jsonl 会在「文件上传」阶段直接报 1210 模型名称错误，
根本轮不到创建 batch 任务。白名单内最强的文本模型是 glm-5.1
（对齐 Claude Opus 4.6 档位、200K 上下文），本脚本用它跑分类：质量优先，
且 Batch 价格为标准 API 的 50%。

运行：python3 main.py
依赖：仅 requests；API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
MODEL = "glm-5.1"  # Batch 白名单内最强的模型；glm-5.3 不支持 Batch，见模块 docstring
BATCH_ENDPOINT = "/v4/chat/completions"  # batch 的 endpoint 字段与 .jsonl 里的 url 都用它

SYSTEM_PROMPT = (
    "你是商品评论情感分类器。把给定的用户评论分为三类：正面、负面、中性。"
    "规则：表达满意、赞扬、有推荐或复购意愿的为正面；"
    "抱怨、不满、投诉、退货的为负面；"
    "客观陈述、褒贬不明显或信息不足的为中性。"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)


def log(msg):
    """进度信息走 stderr，保证 stdout 只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def find_comments_file():
    """在当前目录、脚本目录及其上级目录里查找 comments.txt。"""
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for d in (start, *start.parents):
            cand = d / "comments.txt"
            if cand.is_file():
                return cand
    sys.exit("[错误] 找不到 comments.txt（已搜索当前目录、脚本目录及各自上级目录）")


def build_requests_jsonl(comments, out_path):
    """每条评论生成一行 batch 请求。

    custom_id 必须唯一且不少于 6 个字符——短了会在文件上传阶段报错
    （未写进文档的坑），所以用 request-001 这种格式。
    """
    lines = []
    for i, comment in enumerate(comments, start=1):
        lines.append(json.dumps({
            "custom_id": f"request-{i:03d}",
            "method": "POST",
            "url": BATCH_ENDPOINT,
            "body": {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"评论：{comment}"},
                ],
                "temperature": 0.1,
            },
        }, ensure_ascii=False))
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_response(what, resp):
    """HTTP 状态码和业务错误（HTTP 200 里带 error/code 字段）都要检查。"""
    try:
        body = resp.json()
    except ValueError:
        body = None
    ok = resp.ok
    if ok and isinstance(body, dict):
        code = body.get("code")
        if body.get("error") is not None or (code is not None and str(code) not in ("0", "200")):
            ok = False
    if not ok:
        detail = body if body is not None else resp.text[:500]
        sys.exit(f"[错误] {what} 失败（HTTP {resp.status_code}）：{detail}")
    return body


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("[错误] 未设置环境变量 ZHIPUAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    comments_path = find_comments_file()
    comments = [ln.strip() for ln in comments_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not comments:
        sys.exit(f"[错误] {comments_path} 里没有有效评论")
    log(f"读取到 {len(comments)} 条评论（{comments_path}）")

    jsonl_path = Path(__file__).resolve().parent / "batch_sentiment_requests.jsonl"
    build_requests_jsonl(comments, jsonl_path)
    log(f"已生成请求文件 {jsonl_path}（模型 {MODEL}）")

    # 1. 上传请求文件：purpose 必须是 batch，文件须为 .jsonl
    with jsonl_path.open("rb") as f:
        upload = check_response(
            "上传请求文件",
            requests.post(
                f"{BASE_URL}/paas/v4/files",
                headers=headers,
                files={"file": (jsonl_path.name, f, "application/json")},
                data={"purpose": "batch"},
                timeout=120,
            ),
        )
    input_file_id = upload["id"]
    log(f"文件上传成功：{input_file_id}")

    # 2. 创建 batch 任务（completion_window 已废弃，不传）
    batch = check_response(
        "创建 batch 任务",
        requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "input_file_id": input_file_id,
                "endpoint": BATCH_ENDPOINT,
                "auto_delete_input_file": True,
                "metadata": {"description": "用户评论情感分类：正面/负面/中性"},
            },
            timeout=120,
        ),
    )
    log(f"batch 任务已创建，状态：{batch.get('status')}")

    # 3. 把 batch 任务 id 打印到 stdout（stdout 仅此一行，方便脚本接管）
    print(batch["id"])


if __name__ == "__main__":
    main()
