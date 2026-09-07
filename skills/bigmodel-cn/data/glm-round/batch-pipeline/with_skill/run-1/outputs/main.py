#!/usr/bin/env python3
"""用智谱 BigModel 的 Batch 批量推理接口做评论情感分类（正面/负面/中性）。

流程：读同目录 comments.txt（每行一条评论）→ 生成 batch_requests.jsonl →
上传（purpose=batch）→ 创建 batch 任务 → 把 batch 任务 id 打印到 stdout。
不等待任务完成；之后可用 GET /paas/v4/batches/{batch_id} 查询进度，
任务 completed 后经 output_file_id 下载结果（custom_id 与输入一一对应）。

依赖：仅 requests。API Key 从环境变量 ZHIPUAI_API_KEY 读取。
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"

# 注意：Batch 只支持一份模型白名单，glm-5.3/glm-5.2 等旗舰目前不在名单内，
# 校验发生在上传 .jsonl 这一步，写错会报 1210「模型名称错误」。
# 默认用白名单内的 glm-4-plus，可用环境变量 BATCH_MODEL 覆盖。
MODEL = os.environ.get("BATCH_MODEL", "glm-4-plus")

# 创建 batch 任务的 endpoint 字段与 .jsonl 每行的 url 字段都用这个值
BATCH_ENDPOINT = "/v4/chat/completions"

JSONL_NAME = "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是评论情感分类器。判断用户给出的评论的情感倾向，"
    "只输出一个词：正面、负面 或 中性，不要输出任何其他内容。"
)


def log(msg):
    """进度信息一律走 stderr，保证 stdout 只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def find_comments_file():
    """依次在脚本所在目录、当前工作目录找 comments.txt。"""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        path = base / "comments.txt"
        if path.is_file():
            return path
    sys.exit("错误：找不到 comments.txt（已尝试脚本所在目录和当前目录）")


def build_requests_file(comments_path, out_path):
    """把每条评论转成一行 batch 请求写入 out_path，返回评论条数。"""
    comments = [
        line.strip()
        for line in comments_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not comments:
        sys.exit("错误：comments.txt 里没有评论")

    with out_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, 1):
            request = {
                # custom_id 必须唯一，且最短 6 个字符（"r1" 这类短 id 上传时直接报 1210）
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
                    "max_tokens": 32,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    return len(comments)


def call(resp):
    """统一处理响应：业务层 {'error': ...} 与 HTTP 层错误都转成可读异常。"""
    try:
        data = resp.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        code = err.get("code") if isinstance(err, dict) else None
        message = err.get("message") if isinstance(err, dict) else err
        raise RuntimeError(f"API 错误（HTTP {resp.status_code}，code={code}）：{message}")
    resp.raise_for_status()
    return data


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit(
            "错误：请先设置环境变量 ZHIPUAI_API_KEY"
            "（在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取）"
        )
    headers = {"Authorization": f"Bearer {api_key}"}

    comments_path = find_comments_file()
    jsonl_path = Path(__file__).resolve().parent / JSONL_NAME
    count = build_requests_file(comments_path, jsonl_path)
    log(f"已生成请求文件 {jsonl_path}（{count} 条评论）")

    # 1. 上传 .jsonl，purpose 必须为 batch；模型名校验也发生在这一步
    with jsonl_path.open("rb") as f:
        uploaded = call(
            requests.post(
                f"{BASE_URL}/paas/v4/files",
                headers=headers,
                files={"file": f},
                data={"purpose": "batch"},
                timeout=120,
            )
        )
    input_file_id = uploaded["id"]
    log(f"上传成功，input_file_id={input_file_id}")

    # 2. 创建 batch 任务（completion_window 已废弃，不传）
    batch = call(
        requests.post(
            f"{BASE_URL}/paas/v4/batches",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "input_file_id": input_file_id,
                "endpoint": BATCH_ENDPOINT,
                "auto_delete_input_file": True,
                "metadata": {"description": "评论情感分类：正面/负面/中性"},
            },
            timeout=120,
        )
    )

    # stdout 只输出 batch 任务 id
    print(batch["id"])


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, RuntimeError) as e:
        sys.exit(f"错误：{e}")
