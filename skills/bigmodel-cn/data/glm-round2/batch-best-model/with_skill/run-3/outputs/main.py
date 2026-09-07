"""用智谱 BigModel Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读 comments.txt -> 构造 .jsonl 请求文件 -> 上传（purpose=batch）-> 创建 batch 任务
-> 把 batch 任务 id 打印到 stdout（不等待任务完成）。

用法：
    export ZHIPUAI_API_KEY=sk-xxx
    python3 main.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.bigmodel.cn/api"
# Batch API 只支持一份模型白名单（glm-5.3/glm-5.2 等旗舰不在其中，会在文件上传
# 阶段报 1210"模型名称错误"）。白名单里能力最强的是 glm-5.1。
MODEL = "glm-5.1"
COMMENTS_FILE = "comments.txt"
JSONL_FILE = "batch_requests.jsonl"
MAX_REQUESTS_PER_BATCH = 50000

SYSTEM_PROMPT = (
    "你是用户评论情感分类器。对给出的用户评论判断整体情感倾向，"
    "只输出以下三个标签之一：正面、负面、中性。"
    "不要输出任何解释、标点或其他内容。"
)


def log(msg: str) -> None:
    """进度信息走 stderr，保证 stdout 只有 batch 任务 id。"""
    print(msg, file=sys.stderr)


def read_comments(path: Path) -> list:
    # utf-8-sig 兼容带 BOM 的文件；跳过空行
    with open(path, encoding="utf-8-sig") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line]


def build_requests(comments: list) -> list:
    requests_rows = []
    for i, comment in enumerate(comments, start=1):
        requests_rows.append(
            {
                # custom_id 必须全文件唯一，且实测最短 6 个字符
                "custom_id": f"request-{i:06d}",
                "method": "POST",
                "url": "/v4/chat/completions",
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    "temperature": 0.1,
                    # 三分类是轻量任务，关闭深度思考省 token；glm-5.1 支持该开关
                    "thinking": {"type": "disabled"},
                    "max_tokens": 512,
                },
            }
        )
    return requests_rows


def write_jsonl(rows: list, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def find_comments_file() -> Path:
    # 先找脚本所在目录，再找当前工作目录
    for directory in (Path(__file__).resolve().parent, Path.cwd()):
        candidate = directory / COMMENTS_FILE
        if candidate.is_file():
            return candidate
    sys.exit(f"找不到 {COMMENTS_FILE}，请把它放在脚本同目录或当前目录下。")


def upload_file(api_key: str, path: Path) -> str:
    with open(path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (path.name, f)},
            data={"purpose": "batch"},
            timeout=300,
        )
    resp.raise_for_status()
    file_id = resp.json().get("id")
    if not file_id:
        sys.exit(f"上传文件失败：{resp.text}")
    return file_id


def create_batch(api_key: str, input_file_id: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "input_file_id": input_file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": True,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    batch = resp.json()
    if not batch.get("id"):
        sys.exit(f"创建 batch 任务失败：{resp.text}")
    return batch


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    comments_path = find_comments_file()
    comments = read_comments(comments_path)
    if not comments:
        sys.exit(f"{comments_path} 里没有有效评论")
    if len(comments) > MAX_REQUESTS_PER_BATCH:
        sys.exit(f"评论数 {len(comments)} 超过单个 batch 文件 {MAX_REQUESTS_PER_BATCH} 条上限")

    rows = build_requests(comments)
    jsonl_path = Path(__file__).resolve().parent / JSONL_FILE
    write_jsonl(rows, jsonl_path)
    log(f"已构造 {len(rows)} 条请求 -> {jsonl_path}")

    file_id = upload_file(api_key, jsonl_path)
    log(f"文件上传成功：{file_id}")

    batch = create_batch(api_key, file_id)
    log(f"batch 任务已创建，状态：{batch.get('status')}")

    # 只把 batch 任务 id 打到 stdout
    print(batch["id"])


if __name__ == "__main__":
    main()
