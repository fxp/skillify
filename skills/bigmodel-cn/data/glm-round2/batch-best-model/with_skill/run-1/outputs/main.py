#!/usr/bin/env python3
"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt（每行一条评论）→ 构造 batch_requests.jsonl
→ 以 purpose=batch 上传文件 → 创建 batch 任务 → 把 batch 任务 id 打印到 stdout。

模型选 glm-5.1：Batch 只支持一份模型白名单，平台旗舰 glm-5.3/glm-5.2 目前
不在白名单内，glm-5.1 是白名单里最新、能力最强的文本模型（Batch 价格为标准 API 的 50%）。

用法：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import os
import sys

import requests

BASE_URL = "https://open.bigmodel.cn/api"
BATCH_ENDPOINT = "/v4/chat/completions"  # 创建任务时的 endpoint 与 jsonl 每行的 url 必须一致
MODEL = "glm-5.1"
COMMENTS_FILE = "comments.txt"
REQUESTS_FILE = "batch_requests.jsonl"

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。对给出的用户评论判断整体情感倾向，"
    "只输出一个词作为标签：正面、负面 或 中性。"
    "规则：褒贬混杂的评论按更主导的一面判断；"
    "客观陈述、无明显褒贬倾向的判为中性。除标签外不要输出任何其他内容。"
)


def log(msg):
    """过程日志走 stderr，保证 stdout 只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def read_comments():
    """读取 comments.txt：每行一条评论，跳过空行。优先当前目录，其次脚本所在目录。"""
    candidates = [
        os.path.join(os.getcwd(), COMMENTS_FILE),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), COMMENTS_FILE),
    ]
    path = next((p for p in candidates if os.path.isfile(p)), None)
    if path is None:
        raise FileNotFoundError(
            "找不到 comments.txt，请把它放在脚本同目录或当前工作目录下（尝试过: %s）"
            % "、".join(candidates)
        )
    with open(path, "r", encoding="utf-8-sig") as f:
        comments = [line.strip() for line in f if line.strip()]
    if not comments:
        raise ValueError("comments.txt 里没有有效评论")
    return comments


def build_batch_requests(comments):
    """把每条评论包装成一行 Batch 请求 JSON。

    custom_id 必须唯一且最短 6 个字符（过短会在上传阶段报 1210），
    因此用 request-001 这种带零填充的格式。
    """
    requests_lines = []
    for idx, comment in enumerate(comments, start=1):
        requests_lines.append(
            {
                "custom_id": "request-%03d" % idx,
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
    with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
        for line in requests_lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return REQUESTS_FILE


def check_response(resp, step):
    """统一检查 HTTP 状态码和响应体里的业务错误（error.code / error.message）。"""
    if not resp.ok:
        raise RuntimeError("%s 失败: HTTP %s %s" % (step, resp.status_code, resp.text))
    data = resp.json()
    error = data.get("error")
    if error:
        raise RuntimeError(
            "%s 失败: 业务错误码 %s: %s" % (step, error.get("code"), error.get("message"))
        )
    return data


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        log("错误: 请先设置环境变量 ZHIPUAI_API_KEY")
        return 1
    headers = {"Authorization": "Bearer %s" % api_key}

    # 1. 构造 .jsonl 请求文件
    comments = read_comments()
    requests_file = build_batch_requests(comments)
    log("已构造 %d 条请求 -> %s（模型: %s）" % (len(comments), requests_file, MODEL))

    # 2. 上传文件（Batch 任务文件必须以 purpose=batch 上传）
    with open(requests_file, "rb") as f:
        upload_resp = requests.post(
            "%s/paas/v4/files" % BASE_URL,
            headers=headers,
            files={"file": f},
            data={"purpose": "batch"},
            timeout=120,
        )
    file_id = check_response(upload_resp, "上传请求文件")["id"]
    log("文件上传成功: %s" % file_id)

    # 3. 创建 batch 任务
    create_resp = requests.post(
        "%s/paas/v4/batches" % BASE_URL,
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"task": "sentiment-classification", "model": MODEL},
        },
        timeout=120,
    )
    batch = check_response(create_resp, "创建 batch 任务")
    log("batch 任务创建成功，状态: %s（任务通常 24 小时内完成，结果文件保留 30 天）" % batch.get("status"))

    # 4. 把 batch 任务 id 打印到 stdout
    print(batch["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
