"""用智谱 BigModel 的 Batch API 批量做用户评论情感分类（正面/负面/中性）。

流程：读取同目录 comments.txt（每行一条评论）→ 构造 .jsonl 请求文件 →
以 purpose=batch 上传 → 创建 batch 任务 → 把 batch 任务 id 打印到 stdout。

模型选型说明：Batch 只支持一份模型白名单（在上传文件这一步就校验），
旗舰 glm-5.3 / glm-5.2 目前均不在名单内；glm-5.1 是名单中能力最强的
文本模型，本脚本用它以最大化分类质量。Batch 价格为标准 API 的 50%。

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
FILES_URL = f"{BASE_URL}/paas/v4/files"
BATCHES_URL = f"{BASE_URL}/paas/v4/batches"

# Batch 模型白名单里最强的文本模型（glm-5.3/glm-5.2 不支持 Batch）。
MODEL = "glm-5.1"

SYSTEM_PROMPT = (
    "你是专业的用户评论情感分类器。对给定的用户评论判断整体情感倾向，"
    "只输出一个词：正面、负面 或 中性。"
    "同时包含表扬和抱怨的评论，按其主要倾向归类；"
    "客观陈述、无明显褒贬倾向的评论归为中性。"
    "除这一个词外，不要输出任何其他内容。"
)


def log(msg: str) -> None:
    """进度信息走 stderr，保证 stdout 只有最终的 batch 任务 id。"""
    print(msg, file=sys.stderr)


def die(action: str, resp: requests.Response) -> None:
    """带上业务错误码/报错信息（如 1210 模型名称错误）再退出。"""
    try:
        detail = json.dumps(resp.json(), ensure_ascii=False)
    except ValueError:
        detail = resp.text[:500]
    sys.exit(f"{action}失败：HTTP {resp.status_code} {detail}")


def find_comments_path() -> Path:
    """优先取脚本同目录下的 comments.txt，找不到再退回当前工作目录。"""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        candidate = base / "comments.txt"
        if candidate.is_file():
            return candidate
    sys.exit("错误：找不到 comments.txt（应与脚本放在同一目录）")


def build_requests_file(comments_path: Path) -> Path:
    """把每条评论写成一行 Batch 请求，返回 .jsonl 文件路径。"""
    comments = [line.strip() for line in comments_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not comments:
        sys.exit("错误：comments.txt 里没有有效评论")

    jsonl_path = comments_path.parent / "batch_requests.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for i, comment in enumerate(comments, start=1):
            request = {
                # custom_id 要求最短 6 个字符，request-001 这种格式符合要求
                "custom_id": f"request-{i:03d}",
                "method": "POST",
                "url": "/v4/chat/completions",
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": comment},
                    ],
                    "temperature": 0.1,
                },
            }
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
    log(f"已构造 {len(comments)} 条请求 -> {jsonl_path}")
    return jsonl_path


def upload_file(jsonl_path: Path, headers: dict) -> str:
    """以 purpose=batch 上传请求文件，返回文件 id。"""
    with jsonl_path.open("rb") as f:
        resp = requests.post(
            FILES_URL,
            headers=headers,
            files={"file": (jsonl_path.name, f)},
            data={"purpose": "batch"},
            timeout=300,
        )
    if not resp.ok:
        die("上传请求文件", resp)
    file_id = resp.json()["id"]
    log(f"文件上传成功：{file_id}")
    return file_id


def create_batch(file_id: str, headers: dict) -> dict:
    """基于已上传文件创建 batch 任务，返回 batch 对象。"""
    resp = requests.post(
        BATCHES_URL,
        headers={**headers, "Content-Type": "application/json"},
        json={
            "input_file_id": file_id,
            "endpoint": "/v4/chat/completions",
            "auto_delete_input_file": False,
            "metadata": {"description": "用户评论情感分类（正面/负面/中性）"},
        },
        timeout=60,
    )
    if not resp.ok:
        die("创建 batch 任务", resp)
    return resp.json()


def main() -> None:
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    comments_path = find_comments_path()
    jsonl_path = build_requests_file(comments_path)
    file_id = upload_file(jsonl_path, headers)
    batch = create_batch(file_id, headers)

    log(f"batch 任务创建成功，状态：{batch.get('status')}")
    print(batch["id"])


if __name__ == "__main__":
    main()
