#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_sentiment.py
===================

用智谱开放平台（bigmodel.cn）的 Batch 批量处理 API 对客户评论做情感分类。

背景与模型选型说明（重要，请先读）
--------------------------------
用户最初要求统一使用 `glm-5.2`（团队其他项目也在用这个模型）。但根据
`bigmodel-cn` 技能包 `references/files-batch.md` 中已用真实调用验证的记录：

    Batch 只支持一份模型白名单，不是平台全部模型。把 body.model 写成白名单
    之外的模型（例如旗舰模型 glm-5.3 / glm-5.2 / glm-image 等），文件会在
    **上传阶段**（POST /paas/v4/files）就被拒绝，业务错误码 1210
    “模型名称错误”。

    截至验证时的白名单：glm-5.1、glm-5-turbo、glm-4、glm-4-0520、glm-4-plus、
    glm-4-long、glm-4-plus-0111、glm-4-air、glm-4-air-0111、glm-4-air-250414、
    glm-4-flash、glm-4-flashx-250414、glm-3-turbo、glm-4v、glm-4v-plus、
    glm-5v-turbo、glm-4v-plus-0111、cogview-3、cogview-3-plus、
    cogview-4-250304、embedding-2、embedding-3、cogvideox、cogvideox-2。

`glm-5.2` 不在这份名单里，因此本脚本 **没有** 按字面要求使用 glm-5.2，
而是改用同一白名单内、适合做简单文本分类任务的 `glm-4-air-250414`
（轻量模型，成本低，白名单内已验证可用）。详见同目录 `notes.md`。

如果你确认自己的账号/API 版本已经把 glm-5.2 加入了 Batch 白名单（名单会
随平台更新变化），把下面 `MODEL` 常量改回 "glm-5.2" 即可，脚本其余逻辑
不需要改动 —— 但请先用一条最小请求实测一次，避免 2000 条整份文件上传
阶段就被拒绝。

完整流程
--------
1. 准备 JSONL 请求文件（每行一个独立请求，包含唯一 custom_id）
2. 上传文件（purpose=batch）
3. 创建 Batch 任务（引用 input_file_id，endpoint=/v4/chat/completions）
4. 轮询任务状态直到终态（completed/failed/expired/cancelled）
5. 下载结果文件（成功结果 output_file_id + 失败结果 error_file_id）
6. 解析结果，输出汇总 CSV

用法
----
    export ZHIPUAI_API_KEY="你的真实 API Key"

    # 1) 先干跑一次，只生成 JSONL、不联网，检查请求格式是否符合预期
    python batch_sentiment.py --input reviews.csv --dry-run

    # 2) 确认无误后正式提交
    python batch_sentiment.py --input reviews.csv

输入文件格式（--input，CSV，UTF-8）：
    review_id,review_text
    r00001,订单处理速度太慢，等了整整一周。
    r00002,客服很耐心，问题解决得很快，很满意。
    ...
如果没有 review_id 列，脚本会用行号自动生成。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

BASE_URL = "https://open.bigmodel.cn/api"
# API Key 一律从环境变量读取，不要硬编码进代码。
# 在 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取。
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

# Batch API 目前只接受一份独立的模型白名单（详见文件顶部说明），
# glm-5.2 不在其中，这里用白名单内、适合文本分类任务的轻量模型替代。
MODEL = "glm-4-air-250414"

# Batch 端点固定，且 .jsonl 每行的 "url" 字段必须与之一致。
BATCH_ENDPOINT = "/v4/chat/completions"

# custom_id 官方要求最短 6 个字符，这里统一用 "review-00001" 这种格式。
CUSTOM_ID_PREFIX = "review-"

ALLOWED_LABELS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是一个专业的电商客户评论情感分类助手。"
    f"请仔细阅读用户给出的单条评论，只输出以下三个标签之一：{'/'.join(ALLOWED_LABELS)}。"
    "不要输出任何解释、标点或其他文字，只输出标签本身。"
)

POLL_INTERVAL_SECONDS = 30  # 官方建议 20-30 秒轮询一次，避免过于频繁
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}

# 单个 batch 文件最多 50,000 个请求且不超过 100MB（2000 条评论远低于此限制）
MAX_REQUESTS_PER_FILE = 50_000


def _headers(json_content: bool = False) -> dict:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"未找到环境变量 {API_KEY_ENV_VAR}，请先执行："
            f"export {API_KEY_ENV_VAR}='你的真实 API Key'"
        )
    headers = {"Authorization": f"Bearer {api_key}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass
class Review:
    review_id: str
    text: str

    @property
    def custom_id(self) -> str:
        return f"{CUSTOM_ID_PREFIX}{self.review_id}"


# --------------------------------------------------------------------------
# 步骤 0：读取评论
# --------------------------------------------------------------------------


def load_reviews(input_path: Path) -> list[Review]:
    """从 CSV 读取评论，列名支持 review_id/review_text，缺 review_id 时自动编号。"""
    if not input_path.exists():
        raise FileNotFoundError(
            f"输入文件不存在：{input_path}\n"
            "请提供一个 UTF-8 编码的 CSV，至少包含 review_text 列，"
            "可选 review_id 列，例如：\n"
            "  review_id,review_text\n"
            "  r00001,订单处理速度太慢，等了整整一周。\n"
        )

    reviews: list[Review] = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "review_text" not in reader.fieldnames:
            raise ValueError("CSV 缺少必需的 review_text 列")
        for idx, row in enumerate(reader, start=1):
            text = (row.get("review_text") or "").strip()
            if not text:
                continue  # 跳过空评论
            review_id = (row.get("review_id") or "").strip() or f"{idx:05d}"
            reviews.append(Review(review_id=review_id, text=text))

    if not reviews:
        raise ValueError(f"{input_path} 中没有读取到任何有效评论")

    if len(reviews) > MAX_REQUESTS_PER_FILE:
        raise ValueError(
            f"单个 batch 文件最多支持 {MAX_REQUESTS_PER_FILE} 条请求，"
            f"当前有 {len(reviews)} 条，请先拆分成多个文件分批提交。"
        )

    return reviews


# --------------------------------------------------------------------------
# 步骤 1：准备 JSONL 请求文件
# --------------------------------------------------------------------------


def build_batch_request_file(reviews: Iterable[Review], jsonl_path: Path) -> Path:
    """把评论列表写成 Batch API 要求的 .jsonl 格式，每行一个独立请求。"""
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with jsonl_path.open("w", encoding="utf-8") as f:
        for review in reviews:
            request_line = {
                "custom_id": review.custom_id,
                "method": "POST",
                "url": BATCH_ENDPOINT,
                "body": {
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": review.text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 16,
                },
            }
            f.write(json.dumps(request_line, ensure_ascii=False) + "\n")
            count += 1
    print(f"[1/6] 已生成 Batch 请求文件：{jsonl_path}（{count} 条请求，模型={MODEL}）")
    return jsonl_path


# --------------------------------------------------------------------------
# 步骤 2：上传文件
# --------------------------------------------------------------------------


def upload_batch_file(jsonl_path: Path) -> str:
    """上传 .jsonl 请求文件，purpose 必须为 batch，返回 file_id。"""
    with jsonl_path.open("rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=_headers(),
            files={"file": (jsonl_path.name, f, "application/jsonl")},
            data={"purpose": "batch"},
            timeout=120,
        )
    resp.raise_for_status()
    file_obj = resp.json()
    file_id = file_obj["id"]
    print(f"[2/6] 文件上传成功，file_id = {file_id}")
    return file_id


# --------------------------------------------------------------------------
# 步骤 3：创建批处理任务
# --------------------------------------------------------------------------


def create_batch(input_file_id: str, description: str = "客户评论情感分类") -> str:
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers=_headers(json_content=True),
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            "auto_delete_input_file": True,
            "metadata": {"project": "customer_review_sentiment", "description": description},
        },
        timeout=60,
    )
    resp.raise_for_status()
    batch = resp.json()
    batch_id = batch["id"]
    print(f"[3/6] Batch 任务已创建，batch_id = {batch_id}，初始状态 = {batch['status']}")
    return batch_id


# --------------------------------------------------------------------------
# 步骤 4：轮询任务状态
# --------------------------------------------------------------------------


def poll_batch(batch_id: str, interval: int = POLL_INTERVAL_SECONDS) -> dict:
    print(f"[4/6] 开始轮询任务状态（每 {interval} 秒一次，任务预计 24 小时内完成）...")
    while True:
        resp = requests.get(f"{BASE_URL}/paas/v4/batches/{batch_id}", headers=_headers(), timeout=60)
        resp.raise_for_status()
        batch = resp.json()
        counts = batch.get("request_counts") or {}
        print(
            f"    状态 = {batch['status']}  "
            f"total={counts.get('total')} completed={counts.get('completed')} failed={counts.get('failed')}"
        )
        if batch["status"] in TERMINAL_STATES:
            return batch
        time.sleep(interval)


# --------------------------------------------------------------------------
# 步骤 5：下载结果文件
# --------------------------------------------------------------------------


def download_file_content(file_id: str, dest_path: Path) -> Path:
    resp = requests.get(f"{BASE_URL}/paas/v4/files/{file_id}/content", headers=_headers(), timeout=120)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(resp.content)
    return dest_path


def download_batch_results(batch: dict, output_dir: Path) -> tuple[Path | None, Path | None]:
    output_path = None
    error_path = None

    if batch.get("output_file_id"):
        output_path = download_file_content(batch["output_file_id"], output_dir / "batch_results.jsonl")
        print(f"[5/6] 成功结果已下载：{output_path}")
    else:
        print("[5/6] 没有 output_file_id（可能全部请求都失败了，或任务未成功完成）")

    if batch.get("error_file_id"):
        error_path = download_file_content(batch["error_file_id"], output_dir / "batch_errors.jsonl")
        print(f"      失败结果已下载：{error_path}")

    return output_path, error_path


# --------------------------------------------------------------------------
# 步骤 6：解析结果，输出汇总 CSV
# --------------------------------------------------------------------------


def parse_results(output_path: Path | None, summary_csv_path: Path) -> None:
    if output_path is None or not output_path.exists():
        print("[6/6] 无成功结果文件，跳过解析。")
        return

    rows = []
    label_counts = {label: 0 for label in ALLOWED_LABELS}
    label_counts["未识别"] = 0

    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            custom_id = record.get("custom_id", "")
            response = record.get("response", {})
            status_code = response.get("status_code")
            content = ""
            if status_code == 200:
                try:
                    content = response["body"]["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError, TypeError):
                    content = ""

            label = content if content in ALLOWED_LABELS else "未识别"
            label_counts[label] = label_counts.get(label, 0) + 1
            rows.append(
                {
                    "custom_id": custom_id,
                    "status_code": status_code,
                    "sentiment": label,
                    "raw_model_output": content,
                }
            )

    summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["custom_id", "status_code", "sentiment", "raw_model_output"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[6/6] 已解析 {len(rows)} 条结果，汇总写入：{summary_csv_path}")
    print("      标签分布：" + ", ".join(f"{k}={v}" for k, v in label_counts.items()))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="用智谱 Batch API 对客户评论做情感分类")
    parser.add_argument(
        "--input", type=Path, required=True, help="评论 CSV 文件路径（需含 review_text 列，可选 review_id 列）"
    )
    parser.add_argument(
        "--workdir", type=Path, default=Path("./batch_workdir"), help="中间文件与结果的输出目录（默认 ./batch_workdir）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成 JSONL 请求文件并本地校验，不联网调用任何 API（用于在没有可用 API Key 时先验证请求格式）",
    )
    parser.add_argument(
        "--poll-interval", type=int, default=POLL_INTERVAL_SECONDS, help="轮询间隔秒数（默认 30）"
    )
    args = parser.parse_args()

    workdir: Path = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)
    jsonl_path = workdir / "batch_requests.jsonl"

    # 步骤 0 + 1：读取评论、准备请求文件
    reviews = load_reviews(args.input)
    print(f"[0/6] 已读取 {len(reviews)} 条评论，来自 {args.input}")
    build_batch_request_file(reviews, jsonl_path)

    if args.dry_run:
        print("\n--dry-run 模式：已在本地生成并校验 JSONL，未调用任何真实 API。")
        print(f"请检查 {jsonl_path} 内容，确认无误后去掉 --dry-run 正式提交。")
        return 0

    # 步骤 2：上传
    input_file_id = upload_batch_file(jsonl_path)

    # 步骤 3：创建任务
    batch_id = create_batch(input_file_id)

    # 步骤 4：轮询
    batch = poll_batch(batch_id, interval=args.poll_interval)

    if batch["status"] != "completed":
        print(f"任务未成功完成，最终状态 = {batch['status']}。")
        # 即使不是 completed，已完成的部分请求仍可能有结果文件，尝试一并下载。

    # 步骤 5：下载结果
    output_path, _error_path = download_batch_results(batch, workdir)

    # 步骤 6：解析汇总
    parse_results(output_path, workdir / "sentiment_summary.csv")

    return 0 if batch["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
