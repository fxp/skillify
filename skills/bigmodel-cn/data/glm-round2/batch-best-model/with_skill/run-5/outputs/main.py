#!/usr/bin/env python3
"""用智谱 BigModel 的 Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt（每行一条评论）→ 构造 .jsonl 请求文件 →
上传（purpose=batch）→ 创建 batch 任务 → 把 batch 任务 id 打印到 stdout。
不等待任务完成、不下载结果。

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

# Batch API 只支持一份模型白名单（在文件上传阶段即校验，白名单外的模型名
# 直接报 1210 "模型名称错误"），旗舰 glm-5.3 / glm-5.2 目前都不在名单内。
# 截至 2026-09 实测，白名单中能力最强的文本模型是 glm-5.1
#（Coding 对齐 Claude Opus 4.6，200K 上下文），故选它以兼顾分类质量与 Batch 半价。
MODEL = "glm-5.1"

# Batch 任务固定走 chat/completions 端点，jsonl 每行的 url 须与之一致。
BATCH_ENDPOINT = "/v4/chat/completions"

# 单个 batch 文件最多 50,000 个请求（平台限制）。
MAX_REQUESTS = 50000

SYSTEM_PROMPT = (
    "你是一个严谨的用户评论情感分类器。对给定的一条用户评论判断情感倾向，"
    "输出且仅输出以下三个标签之一：正面、负面、中性。\n"
    "判定规则：表达满意、赞扬、推荐、复购意愿的为「正面」；"
    "表达不满、抱怨、批评、要求退换货的为「负面」；"
    "客观陈述无明显褒贬、正负评价混杂难以权衡、或与情感无关的为「中性」。\n"
    "不要输出任何解释、引号、标点或其他多余文字，只输出标签本身。"
)

SCRIPT_DIR = Path(__file__).resolve().parent
COMMENTS_FILENAME = "comments.txt"
REQUESTS_FILENAME = "batch_requests.jsonl"
TIMEOUT_SECONDS = 120


def log(msg: str) -> None:
    """进度信息走 stderr，保证 stdout 里只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr, flush=True)


def die(msg: str) -> None:
    log(f"错误：{msg}")
    sys.exit(1)


def find_comments_file() -> Path:
    """优先取脚本同目录下的 comments.txt，找不到再退回当前工作目录。"""
    for candidate in (SCRIPT_DIR / COMMENTS_FILENAME, Path.cwd() / COMMENTS_FILENAME):
        if candidate.is_file():
            return candidate
    die(
        f"找不到 {COMMENTS_FILENAME}（已尝试 {SCRIPT_DIR} 和当前工作目录），"
        "请把评论文件放在脚本同目录下"
    )


def read_comments(path: Path) -> list:
    """读取评论：每行一条，去掉首尾空白，跳过空行。"""
    comments = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            text = line.strip()
            if text:
                comments.append((lineno, text))
    if not comments:
        die(f"{path} 里没有读到任何评论")
    return comments


def build_batch_requests(comments: list) -> list:
    """把每条评论包装成 Batch 请求行。

    custom_id 要求全文件唯一且最短 6 个字符（过短会在上传时报 1210），
    这里用 request-<六位行号>，便于结果文件与原始行号一一对应。
    """
    requests_lines = []
    for lineno, text in comments:
        requests_lines.append(
            {
                "custom_id": f"request-{lineno:06d}",
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"评论：{text}\n请输出情感标签（正面/负面/中性）：",
                        },
                    ],
                    "temperature": 0.1,
                },
            }
        )
    return requests_lines


def write_jsonl(path: Path, items: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def check_response(resp: requests.Response, action: str) -> dict:
    """统一校验：HTTP 状态码 + 平台业务错误体（error.code / error.message）。"""
    if resp.status_code >= 400:
        die(f"{action}失败：HTTP {resp.status_code}，响应：{resp.text[:500]}")
    try:
        data = resp.json()
    except ValueError:
        die(f"{action}失败：响应不是 JSON，内容：{resp.text[:500]}")
    error = data.get("error")
    if error:
        die(
            f"{action}失败：业务错误码 {error.get('code')}，"
            f"信息：{error.get('message')}"
        )
    return data


def upload_file(api_key: str, path: Path) -> str:
    """上传 .jsonl 请求文件（必须 purpose=batch），返回文件 id。"""
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f, "application/json")},
            data={"purpose": "batch"},
            timeout=TIMEOUT_SECONDS,
        )
    data = check_response(resp, "上传请求文件")
    file_id = data.get("id")
    if not file_id:
        die(f"上传响应里没有文件 id：{data}")
    return file_id


def create_batch(api_key: str, input_file_id: str) -> str:
    """基于已上传文件创建 batch 任务，返回 batch 任务 id。"""
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=TIMEOUT_SECONDS,
    )
    data = check_response(resp, "创建 batch 任务")
    batch_id = data.get("id")
    if not batch_id:
        die(f"创建响应里没有 batch id：{data}")
    return batch_id


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        die("环境变量 ZHIPUAI_API_KEY 未设置，请先 export ZHIPUAI_API_KEY=你的Key")

    comments_path = find_comments_file()
    comments = read_comments(comments_path)
    if len(comments) > MAX_REQUESTS:
        die(f"评论共 {len(comments)} 条，超过单个 batch 文件 {MAX_REQUESTS} 条的上限")
    log(f"从 {comments_path} 读取到 {len(comments)} 条评论")

    requests_path = SCRIPT_DIR / REQUESTS_FILENAME
    write_jsonl(requests_path, build_batch_requests(comments))
    log(f"已生成 Batch 请求文件 {requests_path}（模型：{MODEL}）")

    file_id = upload_file(api_key, requests_path)
    log(f"请求文件上传成功：{file_id}")

    batch_id = create_batch(api_key, file_id)
    log(f"batch 任务创建成功，状态：validating（任务 24 小时内完成，半价计费）")

    # 仅向 stdout 输出 batch 任务 id，方便上游脚本直接捕获。
    print(batch_id)


if __name__ == "__main__":
    main()
