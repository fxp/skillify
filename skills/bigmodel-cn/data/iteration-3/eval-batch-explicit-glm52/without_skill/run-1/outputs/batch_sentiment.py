#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_sentiment.py
===================

用智谱 (Zhipu AI / bigmodel.cn) 的 Batch 批量处理接口，对客户评论做情感分类。

背景 / 设计取舍
----------------
- 2000 条评论不需要实时返回结果，用 Batch 接口而不是同步 chat.completions，
  可以避免占用实时并发额度，并且智谱的 Batch 定价通常比同步调用更便宜。
- 模型固定使用 `glm-5.2`（见下方 DEFAULT_MODEL 常量），这是按你的要求写死的。
  **重要提示**：截至本脚本编写时，我无法从自身知识库中独立确认 "glm-5.2" 是
  bigmodel.cn 上一个真实存在、当前可用的模型标识符（我的训练数据里最新的智谱
  模型是 GLM-4 / GLM-4.5 / GLM-4.6 系列）。因为你说"其他项目都在用这个模型"，
  这里按你的要求原样使用，但请在正式跑批之前，去 bigmodel.cn 控制台的模型列表
  核对一下这个模型 ID 拼写是否正确、你的账号是否对该模型开通了 Batch 权限。
  如果模型名不对，整个 Batch 任务会在 validating 阶段直接失败，不会浪费太多钱，
  但会浪费轮询等待的时间。为了方便调整，模型名统一从 DEFAULT_MODEL 常量 /
  --model 命令行参数读取，改起来只需要改一个地方。

整体流程（对应智谱 Batch API 的标准用法，接口形态与 OpenAI 的 Batch API 基本对齐）：
  1. prepare  - 读取 2000 条评论，拼成一个 JSONL 请求文件，每行一个独立的
                chat.completions 请求，带唯一 custom_id。
  2. upload   - 把 JSONL 文件上传到智谱（purpose="batch"），拿到 file_id。
  3. create   - 用 file_id 创建 Batch 任务（endpoint=/v4/chat/completions，
                completion_window=24h），拿到 batch_id。
  4. poll     - 轮询 Batch 任务状态，直到 completed / failed / expired / cancelled。
  5. download - 任务完成后下载 output_file_id（以及可能存在的 error_file_id）
                对应的结果文件，解析成一份 CSV，每条评论对应一个情感标签。

依赖
----
    pip install zhipuai

环境变量
--------
    ZHIPU_API_KEY   你的智谱 API Key（占位，不要把真实 key 写进代码或提交到 git）

用法示例
--------
    # 1. 用示例数据跑一遍完整流程（准备 -> 上传 -> 创建 -> 轮询 -> 下载 -> 解析）
    export ZHIPU_API_KEY="your-real-api-key"
    python batch_sentiment.py run --input reviews.csv --output-dir ./batch_run_1

    # 2. 如果脚本中途退出（比如轮询等了很久你 Ctrl+C 了），可以用已保存的 batch_id 续跑
    python batch_sentiment.py run --input reviews.csv --output-dir ./batch_run_1 --resume

    # 3. 只想先看看生成的请求文件对不对，不实际调用 API
    python batch_sentiment.py prepare --input reviews.csv --output-dir ./batch_run_1

输入文件格式
------------
    --input 支持两种格式，按扩展名自动识别：
    - .csv : 需要包含表头，至少有一列评论正文。默认列名是 "review_text"，
             如果有 "review_id" 列会用作稳定的 ID，没有则用行号自动生成
             （review_id 会通过 --id-col / --text-col 自定义列名）。
    - .txt : 每行一条评论，行号（从 1 开始）作为 review_id。
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    from zhipuai import ZhipuAI
except ImportError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "未安装 zhipuai SDK。请先运行: pip install zhipuai"
    ) from exc


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 按用户要求统一使用 GLM-5.2。如果之后要切换模型（或者发现这个模型 ID 不对），
# 只需要改这一个常量，或者运行时传 --model 覆盖。
DEFAULT_MODEL = "glm-5.2"

# 智谱读取 API Key 的环境变量名。不要把真实 key 硬编码进代码。
API_KEY_ENV_VAR = "ZHIPU_API_KEY"

# Batch 任务对应的同步接口地址（智谱 Batch API 里每条请求都要声明自己对应
# 哪个同步 endpoint，这里固定用 chat/completions）。
BATCH_ENDPOINT = "/v4/chat/completions"

# 完成时限。智谱 Batch 目前主要支持 "24h"。
COMPLETION_WINDOW = "24h"

# 允许的情感标签，写进 prompt 里约束模型的输出，方便后续解析。
SENTIMENT_LABELS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是一个专业的客户评论情感分析助手。给定一条客户评论，"
    f"请判断其情感倾向，只能从以下三个标签中选一个：{ '/'.join(SENTIMENT_LABELS) }。\n"
    "严格按如下 JSON 格式输出，不要输出任何多余的文字、解释或 markdown 代码块：\n"
    '{"sentiment": "正面" | "负面" | "中性"}'
)

# 轮询相关的默认参数
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_POLL_TIMEOUT_SECONDS = 24 * 60 * 60  # 最长等 24 小时，和 completion_window 对齐

# 简单的 API 调用重试参数（针对上传 / 创建任务这种偶发网络抖动，不针对轮询本身）
MAX_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 2

# 终止态（Batch 任务不会再变化的状态）
TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("batch_sentiment")


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Review:
    review_id: str
    text: str


# --------------------------------------------------------------------------
# 1. 读取评论 & 生成 Batch 请求文件
# --------------------------------------------------------------------------

def read_reviews(
    input_path: Path,
    text_col: str = "review_text",
    id_col: str = "review_id",
) -> list[Review]:
    """从 CSV 或纯文本文件读取评论列表。"""
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    reviews: list[Review] = []

    if input_path.suffix.lower() == ".csv":
        with input_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if text_col not in (reader.fieldnames or []):
                raise ValueError(
                    f"CSV 文件缺少列 '{text_col}'，实际列为: {reader.fieldnames}"
                )
            for idx, row in enumerate(reader, start=1):
                text = (row.get(text_col) or "").strip()
                if not text:
                    logger.warning("第 %d 行评论为空，已跳过", idx)
                    continue
                rid = (row.get(id_col) or "").strip() or f"row-{idx}"
                reviews.append(Review(review_id=rid, text=text))
    else:
        # 纯文本，每行一条评论
        with input_path.open("r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue
                reviews.append(Review(review_id=f"row-{idx}", text=text))

    if not reviews:
        raise ValueError("没有读取到任何有效评论，请检查输入文件内容和列名。")

    logger.info("读取到 %d 条评论", len(reviews))
    return reviews


def build_request_line(review: Review, model: str) -> dict:
    """构造 Batch JSONL 里的一行请求，格式对齐同步 chat.completions 接口。"""
    return {
        "custom_id": review.review_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": review.text},
            ],
            "temperature": 0.0,
            "max_tokens": 50,
        },
    }


def write_batch_jsonl(reviews: Iterable[Review], out_path: Path, model: str) -> int:
    """把评论列表写成 Batch 请求 JSONL 文件，返回写入的行数。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for review in reviews:
            line = build_request_line(review, model)
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            count += 1
    logger.info("已生成 Batch 请求文件: %s (%d 行)", out_path, count)
    return count


# --------------------------------------------------------------------------
# 通用重试包装
# --------------------------------------------------------------------------

def with_retries(func, *args, what: str = "API 调用", **kwargs):
    """对偶发网络 / 限流错误做简单的指数退避重试。"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 这里故意兜底所有异常做重试
            last_exc = exc
            wait = RETRY_BACKOFF_BASE_SECONDS ** attempt
            logger.warning(
                "%s 第 %d/%d 次尝试失败: %s，%d 秒后重试",
                what, attempt, MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"{what} 重试 {MAX_RETRIES} 次后仍然失败") from last_exc


# --------------------------------------------------------------------------
# 2. 上传文件
# --------------------------------------------------------------------------

def upload_batch_file(client: ZhipuAI, jsonl_path: Path) -> str:
    """上传 Batch 请求文件，返回 file_id。"""
    logger.info("正在上传请求文件: %s", jsonl_path)

    def _do_upload():
        with jsonl_path.open("rb") as f:
            return client.files.create(file=f, purpose="batch")

    result = with_retries(_do_upload, what="上传 Batch 请求文件")
    file_id = result.id
    logger.info("上传完成，file_id = %s", file_id)
    return file_id


# --------------------------------------------------------------------------
# 3. 创建 Batch 任务
# --------------------------------------------------------------------------

def create_batch_job(
    client: ZhipuAI,
    input_file_id: str,
    description: str = "客户评论情感分类批处理任务",
) -> str:
    """创建 Batch 任务，返回 batch_id。"""

    def _do_create():
        return client.batches.create(
            input_file_id=input_file_id,
            endpoint=BATCH_ENDPOINT,
            completion_window=COMPLETION_WINDOW,
            metadata={"description": description},
        )

    batch = with_retries(_do_create, what="创建 Batch 任务")
    logger.info("Batch 任务已创建，batch_id = %s，初始状态 = %s", batch.id, batch.status)
    return batch.id


# --------------------------------------------------------------------------
# 4. 轮询状态
# --------------------------------------------------------------------------

def poll_batch(
    client: ZhipuAI,
    batch_id: str,
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
):
    """轮询 Batch 任务直到进入终止状态，返回最终的 batch 对象。"""
    start = time.monotonic()
    last_status = None

    while True:
        batch = with_retries(client.batches.retrieve, batch_id, what="查询 Batch 状态")
        status = batch.status

        if status != last_status:
            counts = getattr(batch, "request_counts", None)
            if counts is not None:
                logger.info(
                    "Batch %s 状态变更: %s -> %s (completed=%s, failed=%s, total=%s)",
                    batch_id, last_status, status,
                    getattr(counts, "completed", "?"),
                    getattr(counts, "failed", "?"),
                    getattr(counts, "total", "?"),
                )
            else:
                logger.info("Batch %s 状态变更: %s -> %s", batch_id, last_status, status)
            last_status = status

        if status in TERMINAL_STATUSES:
            return batch

        if time.monotonic() - start > timeout_seconds:
            raise TimeoutError(
                f"轮询 Batch {batch_id} 超时（{timeout_seconds} 秒），"
                f"当前状态仍为 {status}。可以稍后用 --resume 继续等待。"
            )

        time.sleep(interval_seconds)


# --------------------------------------------------------------------------
# 5. 下载结果 & 解析
# --------------------------------------------------------------------------

def download_file(client: ZhipuAI, file_id: str, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    def _do_download():
        return client.files.content(file_id)

    content = with_retries(_do_download, what=f"下载文件 {file_id}")
    # zhipuai SDK 的 files.content 返回对象通常带 write_to_file 方法
    # （与 OpenAI SDK 的用法一致）；如果 SDK 版本不同，退化为直接写 bytes/text。
    if hasattr(content, "write_to_file"):
        content.write_to_file(str(dest_path))
    else:
        mode = "wb" if isinstance(getattr(content, "content", b""), (bytes, bytearray)) else "w"
        with dest_path.open(mode) as f:
            f.write(content.content if hasattr(content, "content") else content)

    logger.info("已下载文件 %s -> %s", file_id, dest_path)
    return dest_path


def parse_batch_output(output_jsonl_path: Path, csv_path: Path) -> None:
    """把 Batch 返回的 JSONL 结果解析成一份易读的 CSV: review_id, sentiment, raw_content, error。"""
    rows = []
    with output_jsonl_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("第 %d 行不是合法 JSON，已跳过: %s", line_no, line[:200])
                continue

            custom_id = record.get("custom_id", "")
            error = record.get("error")
            sentiment = ""
            raw_content = ""

            if error:
                rows.append({
                    "review_id": custom_id,
                    "sentiment": "",
                    "raw_content": "",
                    "error": json.dumps(error, ensure_ascii=False),
                })
                continue

            try:
                response_body = record["response"]["body"]
                raw_content = response_body["choices"][0]["message"]["content"]
                # 模型被要求输出 {"sentiment": "..."} 这样的 JSON，这里尽量解析；
                # 解析失败就把原始文本留着，方便人工核对。
                parsed = json.loads(raw_content)
                sentiment = parsed.get("sentiment", "")
                if sentiment not in SENTIMENT_LABELS:
                    logger.warning(
                        "custom_id=%s 返回了非预期标签: %r，已原样保留", custom_id, sentiment
                    )
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("custom_id=%s 解析结果失败: %s", custom_id, exc)

            rows.append({
                "review_id": custom_id,
                "sentiment": sentiment,
                "raw_content": raw_content,
                "error": "",
            })

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["review_id", "sentiment", "raw_content", "error"])
        writer.writeheader()
        writer.writerows(rows)

    logger.info("已解析 %d 条结果 -> %s", len(rows), csv_path)


# --------------------------------------------------------------------------
# 状态文件（用于中断后 --resume）
# --------------------------------------------------------------------------

def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def get_client() -> ZhipuAI:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise SystemExit(
            f"未找到环境变量 {API_KEY_ENV_VAR}。请先执行:\n"
            f'  export {API_KEY_ENV_VAR}="你的真实智谱 API Key"'
        )
    return ZhipuAI(api_key=api_key)


def cmd_prepare(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    reviews = read_reviews(Path(args.input), text_col=args.text_col, id_col=args.id_col)
    if args.limit:
        reviews = reviews[: args.limit]
    write_batch_jsonl(reviews, output_dir / "batch_requests.jsonl", model=args.model)


def cmd_run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "batch_state.json"
    requests_path = output_dir / "batch_requests.jsonl"
    output_jsonl_path = output_dir / "batch_output.jsonl"
    error_jsonl_path = output_dir / "batch_errors.jsonl"
    result_csv_path = output_dir / "sentiment_results.csv"

    state = load_state(state_path) if args.resume else {}
    client = get_client()

    # 步骤 1: 准备请求文件（--resume 时如果已经有 file_id 就跳过，避免重复生成/上传）
    if "input_file_id" not in state:
        reviews = read_reviews(Path(args.input), text_col=args.text_col, id_col=args.id_col)
        if args.limit:
            reviews = reviews[: args.limit]
        n = write_batch_jsonl(reviews, requests_path, model=args.model)
        state["request_count"] = n

        # 步骤 2: 上传
        file_id = upload_batch_file(client, requests_path)
        state["input_file_id"] = file_id
        save_state(state_path, state)
    else:
        logger.info("检测到已保存的 input_file_id=%s，跳过重新生成/上传", state["input_file_id"])

    # 步骤 3: 创建 Batch 任务（--resume 时如果已有 batch_id 就跳过）
    if "batch_id" not in state:
        batch_id = create_batch_job(
            client, state["input_file_id"], description=args.description
        )
        state["batch_id"] = batch_id
        save_state(state_path, state)
    else:
        logger.info("检测到已保存的 batch_id=%s，直接继续轮询", state["batch_id"])

    # 步骤 4: 轮询状态
    batch = poll_batch(
        client,
        state["batch_id"],
        interval_seconds=args.poll_interval,
        timeout_seconds=args.poll_timeout,
    )

    if batch.status != "completed":
        logger.error(
            "Batch 任务未成功完成，最终状态 = %s。详情: %s",
            batch.status, getattr(batch, "errors", None),
        )
        # 即便失败，也尝试把 error_file（如果有）下载下来方便排查
        if getattr(batch, "error_file_id", None):
            download_file(client, batch.error_file_id, error_jsonl_path)
        save_state(state_path, {**state, "final_status": batch.status})
        sys.exit(1)

    # 步骤 5: 下载并解析结果
    if not batch.output_file_id:
        raise RuntimeError("Batch 状态为 completed，但没有 output_file_id，无法下载结果。")

    download_file(client, batch.output_file_id, output_jsonl_path)
    if getattr(batch, "error_file_id", None):
        download_file(client, batch.error_file_id, error_jsonl_path)

    parse_batch_output(output_jsonl_path, result_csv_path)

    state["final_status"] = "completed"
    state["output_file_id"] = batch.output_file_id
    save_state(state_path, state)

    logger.info("全部完成！情感分类结果已写入: %s", result_csv_path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用智谱 Batch 接口对客户评论做情感分类",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", required=True, help="评论输入文件路径 (.csv 或 .txt)")
    common.add_argument("--output-dir", required=True, help="中间文件 / 结果输出目录")
    common.add_argument("--text-col", default="review_text", help="CSV 中评论正文所在列名")
    common.add_argument("--id-col", default="review_id", help="CSV 中评论 ID 所在列名（可选）")
    common.add_argument("--model", default=DEFAULT_MODEL, help=f"使用的模型，默认 {DEFAULT_MODEL}")
    common.add_argument("--limit", type=int, default=None, help="仅处理前 N 条评论，方便小规模测试")

    p_prepare = sub.add_parser("prepare", parents=[common], help="只生成 Batch 请求 JSONL 文件，不调用 API")
    p_prepare.set_defaults(func=cmd_prepare)

    p_run = sub.add_parser("run", parents=[common], help="执行完整流程：准备 -> 上传 -> 创建 -> 轮询 -> 下载 -> 解析")
    p_run.add_argument("--description", default="客户评论情感分类批处理任务", help="Batch 任务的 metadata 描述")
    p_run.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS, help="轮询间隔（秒）")
    p_run.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_SECONDS, help="最长轮询等待时间（秒）")
    p_run.add_argument(
        "--resume", action="store_true",
        help="从 output-dir/batch_state.json 中已保存的 file_id/batch_id 继续（跳过重复上传/创建）",
    )
    p_run.set_defaults(func=cmd_run)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
