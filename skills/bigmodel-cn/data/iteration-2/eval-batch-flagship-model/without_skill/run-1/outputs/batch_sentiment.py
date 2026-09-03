#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_sentiment.py
===================

用智谱 AI（BigModel.cn）的 Batch 批量处理接口，对大批量客户评论做情感分类。

为什么用 Batch 接口
--------------------
- 2000 条评论不需要实时返回结果，用同步 /chat/completions 调用既慢又贵，
  还会占用账号的实时并发 / QPS 额度，可能影响线上其它业务。
- Batch 接口价格通常比同步调用有折扣（各家云厂商的批处理接口一般都是
  官网标价的 5 折左右，具体以 bigmodel.cn 官网当前定价为准），且不占用
  实时并发，是"离线、大批量、非实时"任务的标准做法。
- 整体流程和 OpenAI 的 Batch API 几乎一致：
    1. 把所有请求拼成一个 JSONL 文件（每行一个独立请求，带 custom_id）
    2. 上传文件，拿到 file_id
    3. 用 file_id 创建 batch 任务，拿到 batch_id
    4. 轮询 batch 状态，直到 completed / failed / expired / cancelled
    5. 用返回的 output_file_id（以及可能的 error_file_id）下载结果文件
    6. 解析 JSONL 结果，按 custom_id 映射回原始评论，写出最终结果表

模型选择
--------
选用 "glm-4.6" —— 截至目前智谱开放平台里最新的旗舰级 GLM 模型（在 GLM-4.5 之后发布，
综合推理 / 指令遵循能力最强的通用对话模型），因为用户明确说"预算允许，要最好的分类质量"。
如果你希望进一步压成本，可以把 MODEL 换成 "glm-4.5-air" 或 "glm-4-flash" 这类轻量模型，
但分类质量（尤其是模糊/反讽/混合情感评论的判断）通常会有所下降。

**注意**：智谱的模型清单和命名会不定期更新，实际运行前请到
https://open.bigmodel.cn/dev/api 或控制台确认当前可用于 Batch 接口的最新旗舰模型名称，
并按需修改下面的 MODEL 常量。

依赖
----
    pip install zhipuai

运行前准备
----------
1. 设置环境变量 ZHIPUAI_API_KEY（真实的智谱 API Key，形如 "xxxxxxxx.yyyyyyyy"）。
   本脚本不包含任何真实 key，也不会真正调用线上接口验证。
2. 准备一个 CSV 输入文件，至少包含一列 review（评论正文），可选一列 id
   （不提供则自动用行号生成 id）。默认路径见 --input 参数。

用法示例
--------
    export ZHIPUAI_API_KEY="你的key"
    python batch_sentiment.py \\
        --input reviews.csv \\
        --output-dir ./batch_run \\
        --poll-interval 30

脚本会在 --output-dir 下生成：
    batch_input.jsonl     上传给智谱的批处理请求文件
    batch_output.jsonl    智谱返回的原始批处理结果（成功的请求）
    batch_errors.jsonl    智谱返回的错误结果（如果有）
    sentiment_results.csv 最终整理好的“评论 -> 情感标签”结果表
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
except ImportError:  # pragma: no cover - 环境未安装依赖时给出清晰提示
    print(
        "缺少依赖 zhipuai，请先执行: pip install zhipuai",
        file=sys.stderr,
    )
    raise


# --------------------------------------------------------------------------
# 全局配置
# --------------------------------------------------------------------------

# 智谱开放平台的最新旗舰对话模型（截至本脚本编写时）。预算允许、追求最佳分类质量时使用。
# 如需省钱可换成 "glm-4.5-air" / "glm-4-flash" 等轻量模型，但准确率可能下降。
MODEL = "glm-4.6"

# Batch 接口对应的同步接口路径。智谱的 Batch 任务需要指定它"代理"哪个同步端点。
BATCH_ENDPOINT = "/v4/chat/completions"

# 官方目前一般只支持 24 小时完成窗口（与 OpenAI Batch API 的约定一致）。
COMPLETION_WINDOW = "24h"

# 允许的情感标签集合，用于校验模型输出、做兜底处理。
ALLOWED_LABELS = {"positive", "negative", "neutral"}

SYSTEM_PROMPT = """你是一个专业的客户评论情感分析引擎。
给定一条客户评论，请判断其整体情感倾向，只能从以下三类中选择一个：
- positive：整体正面、满意、好评
- negative：整体负面、不满、差评、投诉
- neutral：中性、无明显情感倾向，或正负面信息基本持平

请只输出一个 JSON 对象，不要输出任何多余文字、解释或 Markdown 代码块标记，格式严格如下：
{"sentiment": "positive|negative|neutral", "confidence": 0到1之间的小数, "reason": "一句话中文理由，不超过30字"}

判断时注意：
- 结合反讽、比较级（"还行，但不会再买了"通常偏 negative）等语气综合判断，不要只看关键词。
- 如果评论同时包含明显更强的负面诉求（如退款、投诉、质量问题），即使夹杂客气话，也应判为 negative。
- confidence 反映你对该判断的把握程度，而不是固定值。
"""


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("batch_sentiment")


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------

@dataclass
class Review:
    review_id: str
    text: str


@dataclass
class SentimentResult:
    review_id: str
    sentiment: Optional[str]
    confidence: Optional[float]
    reason: Optional[str]
    raw_error: Optional[str] = None


# --------------------------------------------------------------------------
# 第 0 步：读取评论
# --------------------------------------------------------------------------

def load_reviews(input_csv: Path) -> list[Review]:
    """从 CSV 文件读取评论。要求至少有一列 'review'，可选一列 'id'。

    如果没有 'id' 列，则用从 1 开始的行号自动生成形如 'review-0001' 的 id。
    """
    reviews: list[Review] = []
    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "review" not in reader.fieldnames:
            raise ValueError(
                f"输入文件 {input_csv} 必须包含表头 'review'（评论正文列），"
                f"实际表头为: {reader.fieldnames}"
            )
        for idx, row in enumerate(reader, start=1):
            text = (row.get("review") or "").strip()
            if not text:
                continue  # 跳过空评论
            rid = (row.get("id") or "").strip() or f"review-{idx:04d}"
            reviews.append(Review(review_id=rid, text=text))

    if not reviews:
        raise ValueError(f"输入文件 {input_csv} 中没有读到任何有效评论")

    logger.info("共读取到 %d 条有效评论", len(reviews))
    return reviews


# --------------------------------------------------------------------------
# 第 1 步：准备批处理请求文件（JSONL）
# --------------------------------------------------------------------------

def build_batch_request_line(review: Review) -> dict:
    """构造单条 Batch 请求，格式仿照 OpenAI/智谱 Batch 接口约定：
    { "custom_id": ..., "method": "POST", "url": ..., "body": {...同步接口参数...} }
    """
    return {
        "custom_id": review.review_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": review.text},
            ],
            # 分类任务要稳定、可复现，温度调低。
            "temperature": 0.1,
            "top_p": 0.7,
            # 让模型直接返回 JSON，减少后续解析的脆弱性。
            "response_format": {"type": "json_object"},
        },
    }


def write_batch_input_file(reviews: Iterable[Review], jsonl_path: Path) -> int:
    count = 0
    with jsonl_path.open("w", encoding="utf-8") as f:
        for review in reviews:
            line = build_batch_request_line(review)
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            count += 1
    logger.info("批处理请求文件已生成: %s (%d 条请求)", jsonl_path, count)
    return count


# --------------------------------------------------------------------------
# 第 2 步：上传文件
# --------------------------------------------------------------------------

def upload_batch_file(client: ZhipuAI, jsonl_path: Path) -> str:
    logger.info("正在上传批处理请求文件: %s", jsonl_path)
    with jsonl_path.open("rb") as f:
        result = client.files.create(file=f, purpose="batch")
    file_id = result.id
    logger.info("文件上传成功, file_id=%s", file_id)
    return file_id


# --------------------------------------------------------------------------
# 第 3 步：创建批处理任务
# --------------------------------------------------------------------------

def create_batch_job(client: ZhipuAI, input_file_id: str) -> str:
    logger.info("正在创建批处理任务 (endpoint=%s, window=%s)...", BATCH_ENDPOINT, COMPLETION_WINDOW)
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint=BATCH_ENDPOINT,
        completion_window=COMPLETION_WINDOW,
        metadata={
            "task": "customer_review_sentiment_classification",
            "model": MODEL,
        },
    )
    logger.info("批处理任务创建成功, batch_id=%s, 初始状态=%s", batch.id, batch.status)
    return batch.id


# --------------------------------------------------------------------------
# 第 4 步：轮询批处理任务状态
# --------------------------------------------------------------------------

# 智谱 Batch 任务可能出现的终态。具体取值以官方文档为准，这里覆盖常见的几种命名。
TERMINAL_SUCCESS_STATES = {"completed"}
TERMINAL_FAILURE_STATES = {"failed", "expired", "cancelled", "cancelling_failed"}


def poll_batch_job(
    client: ZhipuAI,
    batch_id: str,
    poll_interval_sec: int = 30,
    timeout_sec: int = 24 * 3600,
):
    """轮询批处理任务状态，直到进入终态或超时。

    Batch 任务不需要实时等待，但脚本仍然提供一个可控的超时兜底（默认 24 小时，
    与 completion_window 对齐），避免无限轮询挂死。生产环境中更推荐把这一步
    换成定时任务（如 cron / 消息队列回调）而不是一直占着一个进程轮询。
    """
    start = time.monotonic()
    last_status = None
    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status

        if status != last_status:
            counts = getattr(batch, "request_counts", None)
            logger.info(
                "batch_id=%s 状态更新: %s%s",
                batch_id,
                status,
                f" (请求统计: {counts})" if counts else "",
            )
            last_status = status

        if status in TERMINAL_SUCCESS_STATES:
            logger.info("批处理任务已完成: %s", batch_id)
            return batch

        if status in TERMINAL_FAILURE_STATES:
            errors = getattr(batch, "errors", None)
            logger.error("批处理任务未成功结束, 状态=%s, errors=%s", status, errors)
            return batch

        elapsed = time.monotonic() - start
        if elapsed > timeout_sec:
            raise TimeoutError(
                f"批处理任务 {batch_id} 轮询超时 ({timeout_sec}s)，当前状态: {status}"
            )

        time.sleep(poll_interval_sec)


# --------------------------------------------------------------------------
# 第 5 步：下载结果文件
# --------------------------------------------------------------------------

def download_file(client: ZhipuAI, file_id: str, dest_path: Path) -> None:
    logger.info("正在下载文件 file_id=%s -> %s", file_id, dest_path)
    content = client.files.content(file_id)
    # zhipuai SDK 的返回对象通常提供 write_to_file；如果版本不同没有该方法，
    # 就退化为直接写二进制内容，兼容性更好。
    if hasattr(content, "write_to_file"):
        content.write_to_file(str(dest_path))
    else:
        data = content.content if hasattr(content, "content") else bytes(content)
        dest_path.write_bytes(data)
    logger.info("下载完成: %s", dest_path)


def download_batch_outputs(client: ZhipuAI, batch, output_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
    output_path = None
    error_path = None

    output_file_id = getattr(batch, "output_file_id", None)
    if output_file_id:
        output_path = output_dir / "batch_output.jsonl"
        download_file(client, output_file_id, output_path)
    else:
        logger.warning("批处理任务没有 output_file_id，可能全部请求都失败了")

    error_file_id = getattr(batch, "error_file_id", None)
    if error_file_id:
        error_path = output_dir / "batch_errors.jsonl"
        download_file(client, error_file_id, error_path)
        logger.warning("存在错误结果文件，已下载到: %s，请检查", error_path)

    return output_path, error_path


# --------------------------------------------------------------------------
# 第 6 步：解析结果，映射回原始评论
# --------------------------------------------------------------------------

def parse_model_content_to_sentiment(review_id: str, content: str) -> SentimentResult:
    """解析模型返回的 JSON 字符串，提取情感标签。带兜底容错，
    避免个别请求返回非严格 JSON 时整个脚本崩溃。
    """
    try:
        parsed = json.loads(content)
        label = str(parsed.get("sentiment", "")).strip().lower()
        if label not in ALLOWED_LABELS:
            raise ValueError(f"非法情感标签: {label!r}")
        confidence = parsed.get("confidence")
        confidence = float(confidence) if confidence is not None else None
        reason = parsed.get("reason")
        return SentimentResult(
            review_id=review_id,
            sentiment=label,
            confidence=confidence,
            reason=reason,
        )
    except Exception as exc:  # noqa: BLE001 - 这里就是要兜住任意解析异常
        logger.warning("解析模型输出失败 (review_id=%s): %s | 原始内容: %r", review_id, exc, content)
        return SentimentResult(
            review_id=review_id,
            sentiment=None,
            confidence=None,
            reason=None,
            raw_error=f"parse_error: {exc}",
        )


def parse_batch_output_file(output_path: Path) -> dict[str, SentimentResult]:
    """解析 batch_output.jsonl，每行形如：
    {
      "id": "...",
      "custom_id": "review-0001",
      "response": {
        "status_code": 200,
        "body": { ... 与同步 /chat/completions 返回结构一致 ... }
      },
      "error": null
    }
    """
    results: dict[str, SentimentResult] = {}
    with output_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("第 %d 行不是合法 JSON，已跳过: %s", line_no, exc)
                continue

            custom_id = record.get("custom_id", f"unknown-line-{line_no}")

            if record.get("error"):
                results[custom_id] = SentimentResult(
                    review_id=custom_id,
                    sentiment=None,
                    confidence=None,
                    reason=None,
                    raw_error=json.dumps(record["error"], ensure_ascii=False),
                )
                continue

            response = record.get("response") or {}
            status_code = response.get("status_code")
            body = response.get("body") or {}

            if status_code != 200:
                results[custom_id] = SentimentResult(
                    review_id=custom_id,
                    sentiment=None,
                    confidence=None,
                    reason=None,
                    raw_error=f"http_status={status_code}, body={body}",
                )
                continue

            try:
                content = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                results[custom_id] = SentimentResult(
                    review_id=custom_id,
                    sentiment=None,
                    confidence=None,
                    reason=None,
                    raw_error=f"unexpected_response_shape: {exc}",
                )
                continue

            results[custom_id] = parse_model_content_to_sentiment(custom_id, content)

    return results


def write_final_results(
    reviews: list[Review],
    results_by_id: dict[str, SentimentResult],
    out_csv_path: Path,
) -> None:
    with out_csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "review", "sentiment", "confidence", "reason", "error"])
        n_ok, n_fail = 0, 0
        for review in reviews:
            res = results_by_id.get(review.review_id)
            if res is None:
                writer.writerow([review.review_id, review.text, "", "", "", "missing_from_batch_output"])
                n_fail += 1
                continue
            if res.sentiment is None:
                writer.writerow(
                    [review.review_id, review.text, "", "", "", res.raw_error or "unknown_error"]
                )
                n_fail += 1
            else:
                writer.writerow(
                    [review.review_id, review.text, res.sentiment, res.confidence, res.reason, ""]
                )
                n_ok += 1

    logger.info("结果已写出到 %s (成功 %d 条, 失败/缺失 %d 条)", out_csv_path, n_ok, n_fail)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run(
    input_csv: Path,
    output_dir: Path,
    poll_interval: int,
    timeout_sec: int,
    api_key: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    client = ZhipuAI(api_key=api_key)

    # 0. 读取评论
    reviews = load_reviews(input_csv)

    # 1. 生成批处理请求文件
    batch_input_path = output_dir / "batch_input.jsonl"
    write_batch_input_file(reviews, batch_input_path)

    # 2. 上传文件
    input_file_id = upload_batch_file(client, batch_input_path)

    # 3. 创建批处理任务
    batch_id = create_batch_job(client, input_file_id)

    # 4. 轮询状态直到完成
    batch = poll_batch_job(
        client,
        batch_id,
        poll_interval_sec=poll_interval,
        timeout_sec=timeout_sec,
    )

    # 5. 下载结果（成功 + 错误文件）
    output_path, error_path = download_batch_outputs(client, batch, output_dir)

    if output_path is None:
        logger.error("没有可用的输出文件，任务可能整体失败，请检查 error 文件和 batch 状态: %s", batch)
        sys.exit(1)

    # 6. 解析并映射回原始评论，写出最终 CSV
    results_by_id = parse_batch_output_file(output_path)
    final_csv_path = output_dir / "sentiment_results.csv"
    write_final_results(reviews, results_by_id, final_csv_path)

    if error_path is not None:
        logger.warning(
            "注意：存在部分请求失败，详情见 %s，你可以针对失败的评论单独重跑（同步接口或再开一个小批次）。",
            error_path,
        )

    logger.info("全部完成。最终结果: %s", final_csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用智谱 AI (BigModel.cn) Batch 接口对客户评论做情感分类",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("reviews.csv"),
        help="输入 CSV 文件路径，需包含表头 'review'（评论正文），可选 'id' 列。默认: reviews.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./batch_run"),
        help="所有中间文件与最终结果的输出目录。默认: ./batch_run",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="轮询批处理任务状态的间隔秒数。默认: 30",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=24 * 3600,
        help="轮询超时时间（秒），默认与 24 小时完成窗口对齐: 86400",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # API Key 一律从环境变量读取，不在代码里硬编码任何真实密钥。
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        logger.error(
            "未找到环境变量 ZHIPUAI_API_KEY，请先执行: export ZHIPUAI_API_KEY='你的真实key'"
        )
        sys.exit(1)

    if not args.input.exists():
        logger.error(
            "输入文件不存在: %s\n"
            "请准备一个 CSV 文件，至少包含表头 'review'（每行一条评论正文），"
            "可选 'id' 列作为评论唯一标识。",
            args.input,
        )
        sys.exit(1)

    try:
        run(
            input_csv=args.input,
            output_dir=args.output_dir,
            poll_interval=args.poll_interval,
            timeout_sec=args.timeout,
            api_key=api_key,
        )
    except Exception:
        logger.exception("批处理流程执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
