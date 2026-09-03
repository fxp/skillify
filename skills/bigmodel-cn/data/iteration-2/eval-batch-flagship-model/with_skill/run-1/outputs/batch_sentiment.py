#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
客户评论情感分类 —— 智谱开放平台（bigmodel.cn）Batch 批量处理脚本
================================================================

用途
----
对约 2000 条客户评论做情感分类（正面 / 负面 / 中性），通过 Batch API 异步批量提交，
而不是对同步接口发起 2000 次并发请求：
  - 价格是标准同步接口的 50%；
  - 不占用模型的实时并发限额（Batch 有独立的排队额度）；
  - 天然适合"不需要立即拿到结果"的离线打标场景。

模型选择：glm-5.1
----------------
Batch API **不支持平台全部模型**，只认一份固定白名单（本技能包 references/files-batch.md
里用真实 API 调用验证过：把白名单外的模型写进 .jsonl 上传时，会在文件上传阶段就被拒绝，
业务错误码 1210 "模型名称错误"）。截至技能文档更新时（2026-09），白名单大致是：

    glm-5.1, glm-5-turbo, glm-4, glm-4-0520, glm-4-plus, glm-4-long, glm-4-plus-0111,
    glm-4-air, glm-4-air-0111, glm-4-air-250414, glm-4-flash, glm-4-flashx-250414,
    glm-3-turbo, glm-4v, glm-4v-plus, glm-5v-turbo, glm-4v-plus-0111,
    cogview-3, cogview-3-plus, cogview-4-250304, embedding-2, embedding-3,
    cogvideox, cogvideox-2

也就是说，models.md 里综合推荐的当前旗舰模型（glm-5.3 / glm-5.2）**不在**这份 Batch 白
名单里，Batch 场景下用不了。在白名单内，纯文本、非视觉模型里最强的是 **glm-5.1**
（官方定位：编程/推理能力对齐 Claude Opus 4.6，可自主处理长程任务），因此本脚本选用
glm-5.1 作为"预算允许、要最好质量"的 Batch 分类模型。

⚠️ 重要不确定性：这份白名单不是官方文档正式发布的稳定列表，而是从一次实测报错信息里
摘出来的，**随时可能随平台更新变化**。脚本里的 `MODEL` 常量因此在 `submit_batch()`
里做了"先小批量探测、失败立刻停止"的设计（见下方 `validate_model_or_die`），并在把
文件上传给 Batch 之前用同一个模型名先探测一次；如果 glm-5.1 哪天也被移出白名单，报错
信息会直接指出允许的模型集合，把 `MODEL` 换成报错信息里给出的名字即可，不要凭记忆猜。
建议长期使用前，先跑一次 `--dry-run`（只构建/上传 3 条样本，不创建正式 batch）确认模型
可用，再对全量 2000 条提交。

工作流程
--------
1. 读取评论（CSV，需含 `review` 列；也可用 --demo 生成演示数据）；
2. 为每条评论生成一行 Batch 请求（JSON 模式输出，严格约束返回结构），写成 .jsonl；
3. 以 purpose=batch 上传该 .jsonl 文件；
4. 用 input_file_id 创建 Batch 任务（endpoint=/v4/chat/completions）；
5. 轮询任务状态（建议间隔 20-30 秒），直到进入终态；
6. 任务完成后下载 output_file_id（成功结果）与 error_file_id（失败请求，如有）；
7. 把结果与原始评论按 custom_id 对齐，写出最终 CSV。

用法示例
--------
    export ZHIPUAI_API_KEY="你的真实API Key"

    # 1) 用演示数据跑一遍完整流程（不会真的调用网络，因为本脚本默认不含真实 Key）
    python batch_sentiment.py --demo --out results.csv

    # 2) 处理自己的 2000 条评论（CSV 需要一列名为 review）
    python batch_sentiment.py --input reviews.csv --out results.csv

注意：本脚本不会在没有真实 API Key 的情况下被这次任务实际执行——`ZHIPUAI_API_KEY`
从环境变量读取，代码里不包含任何真实密钥。
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

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

BASE_URL = "https://open.bigmodel.cn/api"
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"  # 永远不要把 Key 硬编码进代码

# 选型见文件头部说明：glm-5.1 是当前 Batch 白名单内能力最强的纯文本旗舰模型。
# 如果未来白名单变化导致上传/创建任务报错（业务错误码 1210），把这里换成报错信息
# 里给出的允许模型名即可。
MODEL = "glm-5.1"

# Batch 端点目前只支持这一个值，.jsonl 每行的 url 字段必须与它一致。
BATCH_ENDPOINT = "/v4/chat/completions"

# 情感分类的取值集合，写死在 prompt 里保证模型输出可控。
SENTIMENT_LABELS = ("正面", "负面", "中性")

SYSTEM_PROMPT = (
    "你是专业的客户评论情感分析专家。给定一条中文或英文客户评论，判断其情感倾向。\n"
    "请严格只输出一个 JSON 对象，不要输出任何多余文字、前后缀或 Markdown 代码块标记，"
    "JSON 结构必须是：\n"
    '{"sentiment": "正面/负面/中性", "confidence": 0.0到1.0之间的数字, '
    '"reason": "不超过20个字的简短理由"}\n'
    f"sentiment 字段只能是这三个值之一：{'/'.join(SENTIMENT_LABELS)}。"
    "如果评论中同时包含正面和负面内容，但整体基调更偏向某一方，选择占主导的情感；"
    "如果评论纯粹是客观陈述、没有明显情感色彩，选择“中性”。"
)

# 轮询间隔（秒）。官方建议 20-30 秒，避免过于频繁请求。
POLL_INTERVAL_SECONDS = 25
# 任务预计 24 小时内完成，超过 7 天未处理完会被平台自动取消；这里给一个宽松上限
# （48 小时），避免脚本无限期挂起，可按需调整。
MAX_POLL_SECONDS = 48 * 60 * 60

TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}


def _headers(json_body: bool = False) -> dict:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"未找到环境变量 {API_KEY_ENV_VAR}，请先 export {API_KEY_ENV_VAR}=你的真实API Key"
        )
    headers = {"Authorization": f"Bearer {api_key}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class Review:
    custom_id: str
    text: str


@dataclass
class ClassificationResult:
    custom_id: str
    review_text: str
    sentiment: str | None
    confidence: float | None
    reason: str | None
    raw_content: str | None
    error: str | None = None


# ---------------------------------------------------------------------------
# 第一步：读取评论
# ---------------------------------------------------------------------------


def load_reviews_from_csv(path: str, text_column: str = "review") -> list[Review]:
    """从 CSV 读取评论列表。要求 CSV 包含表头，且有一列名为 text_column（默认 review）。"""
    reviews: list[Review] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if text_column not in (reader.fieldnames or []):
            raise ValueError(
                f"CSV 缺少列 '{text_column}'，实际表头为：{reader.fieldnames}"
            )
        for i, row in enumerate(reader):
            text = (row.get(text_column) or "").strip()
            if not text:
                continue
            reviews.append(Review(custom_id=f"review-{i:06d}", text=text))
    if not reviews:
        raise ValueError(f"未从 {path} 读到任何非空评论")
    return reviews


def demo_reviews(n: int = 20) -> list[Review]:
    """生成一批演示评论，方便在没有真实数据时跑通全流程。"""
    samples = [
        "订单处理速度太慢，等了整整一周才发货，非常失望。",
        "客服很耐心，问题很快就解决了，体验很好！",
        "商品收到了，包装完整，功能符合描述。",
        "质量很差，用了两天就坏了，要求退货退款。",
        "物流很快，第二天就到了，包装也很仔细，赞一个。",
        "客服态度冷淡，问了半天也没解决我的问题。",
        "价格有点贵，但是质量确实对得起价格。",
        "这是我买过最好用的产品，会继续回购。",
        "说明书写得不清楚，安装花了很长时间。",
        "整体还可以，没有特别惊喜也没有特别失望。",
    ]
    out = []
    for i in range(n):
        out.append(Review(custom_id=f"demo-{i:06d}", text=samples[i % len(samples)]))
    return out


# ---------------------------------------------------------------------------
# 第二步：构建 Batch 请求文件（.jsonl）
# ---------------------------------------------------------------------------


def build_batch_request_line(review: Review) -> dict:
    return {
        "custom_id": review.custom_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": review.text},
            ],
            # 低温度，保证同一条评论多次分类结果稳定、可复现。
            "temperature": 0.1,
            # JSON 模式：让 choices[0].message.content 直接是可 json.loads 的字符串。
            "response_format": {"type": "json_object"},
            # glm-5.1 支持深度思考（模型自动判断/可显式开关，非强制）。预算允许、
            # 追求最高分类质量时显式开启，让模型在给结论前先做一步推理判断。
            # 注意：reasoning_effort 参数仅 glm-5.2 及以上支持，glm-5.1 不要传，
            # 否则可能报参数错误。
            "thinking": {"type": "enabled"},
        },
    }


def write_batch_jsonl(reviews: Iterable[Review], out_path: str) -> str:
    count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for review in reviews:
            line = build_batch_request_line(review)
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            count += 1
    print(f"[1/6] 已生成 Batch 请求文件：{out_path}（{count} 条请求）")
    # Batch 单文件限制：≤50,000 请求 且 ≤100MB。2000 条量级远在限制之内，这里只是
    # 做个防御性检查，避免误传超大文件。
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    if count > 50_000 or size_mb > 100:
        raise ValueError(
            f"请求文件超出 Batch 单文件限制（{count} 条 / {size_mb:.1f}MB，"
            "上限为 50,000 条且 ≤100MB），请拆分成多个 Batch 任务分别提交。"
        )
    return out_path


# ---------------------------------------------------------------------------
# 第三步：上传文件
# ---------------------------------------------------------------------------


def upload_batch_file(jsonl_path: str) -> str:
    with open(jsonl_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/paas/v4/files",
            headers=_headers(),
            files={"file": f},
            data={"purpose": "batch"},
            timeout=60,
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"上传 Batch 请求文件失败（HTTP {resp.status_code}）：{resp.text}\n"
            "如果报错信息里出现业务错误码 1210 / '模型名称错误'，说明脚本里的 MODEL "
            "常量已不在当前 Batch 白名单内，请按报错信息里给出的允许模型列表更换 MODEL。"
        )
    file_obj = resp.json()
    file_id = file_obj["id"]
    print(f"[2/6] 文件上传成功，file_id = {file_id}")
    return file_id


# ---------------------------------------------------------------------------
# 第四步：创建 Batch 任务
# ---------------------------------------------------------------------------


def create_batch(input_file_id: str, description: str = "客户评论情感分类") -> str:
    resp = requests.post(
        f"{BASE_URL}/paas/v4/batches",
        headers=_headers(json_body=True),
        json={
            "input_file_id": input_file_id,
            "endpoint": BATCH_ENDPOINT,
            # 任务创建成功后原始输入文件对我们已无用处，让平台自动清理，节省文件配额
            # （Batch 类型文件每账号上传数量有上限）。
            "auto_delete_input_file": True,
            "metadata": {"project": "customer_review_sentiment", "description": description},
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"创建 Batch 任务失败（HTTP {resp.status_code}）：{resp.text}")
    batch = resp.json()
    batch_id = batch["id"]
    print(f"[3/6] Batch 任务已创建，batch_id = {batch_id}，初始状态 = {batch.get('status')}")
    return batch_id


# ---------------------------------------------------------------------------
# 第五步：轮询任务状态
# ---------------------------------------------------------------------------


def poll_batch(batch_id: str) -> dict:
    print(f"[4/6] 开始轮询任务状态（每 {POLL_INTERVAL_SECONDS} 秒查询一次）...")
    start = time.time()
    last_status = None
    while True:
        resp = requests.get(
            f"{BASE_URL}/paas/v4/batches/{batch_id}", headers=_headers(), timeout=30
        )
        resp.raise_for_status()
        batch = resp.json()
        status = batch.get("status")
        counts = batch.get("request_counts") or {}
        if status != last_status:
            print(
                f"    状态变化: {last_status} -> {status} "
                f"(completed={counts.get('completed')}, failed={counts.get('failed')}, "
                f"total={counts.get('total')})"
            )
            last_status = status

        if status in TERMINAL_STATES:
            return batch

        if time.time() - start > MAX_POLL_SECONDS:
            raise TimeoutError(
                f"轮询超过 {MAX_POLL_SECONDS / 3600:.0f} 小时仍未进入终态（当前状态：{status}），"
                f"脚本已停止轮询，但任务仍在平台侧继续处理，可稍后用 batch_id={batch_id} 手动查询。"
            )

        time.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# 第六步：下载结果文件
# ---------------------------------------------------------------------------


def download_file_content(file_id: str, out_path: str) -> str:
    resp = requests.get(
        f"{BASE_URL}/paas/v4/files/{file_id}/content", headers=_headers(), timeout=120
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return out_path


def parse_output_jsonl(path: str) -> dict[str, dict]:
    """把 Batch 输出 .jsonl 解析成 {custom_id: response_body} 的映射。"""
    results: dict[str, dict] = {}
    if not path or not os.path.exists(path):
        return results
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            results[row["custom_id"]] = row
    return results


# ---------------------------------------------------------------------------
# 汇总输出结果
# ---------------------------------------------------------------------------


def build_final_results(
    reviews: list[Review], output_rows: dict[str, dict], error_rows: dict[str, dict]
) -> list[ClassificationResult]:
    final: list[ClassificationResult] = []
    for review in reviews:
        row = output_rows.get(review.custom_id)
        err_row = error_rows.get(review.custom_id)

        if row is not None:
            try:
                status_code = row["response"]["status_code"]
                message = row["response"]["body"]["choices"][0]["message"]
                content = message["content"]
                if status_code != 200:
                    final.append(
                        ClassificationResult(
                            custom_id=review.custom_id,
                            review_text=review.text,
                            sentiment=None,
                            confidence=None,
                            reason=None,
                            raw_content=content,
                            error=f"HTTP {status_code}",
                        )
                    )
                    continue
                parsed = json.loads(content)
                sentiment = parsed.get("sentiment")
                if sentiment not in SENTIMENT_LABELS:
                    # 模型偶尔可能不完全遵循约束，做一次宽松归一化，归一化失败则原样保留
                    # 并标记，方便人工复查（见 files-batch.md 里关于 json_object 不是
                    # 强约束、需要二次校验的提示）。
                    sentiment = sentiment or "未知"
                final.append(
                    ClassificationResult(
                        custom_id=review.custom_id,
                        review_text=review.text,
                        sentiment=sentiment,
                        confidence=parsed.get("confidence"),
                        reason=parsed.get("reason"),
                        raw_content=content,
                        error=None,
                    )
                )
            except (KeyError, IndexError, json.JSONDecodeError) as exc:
                final.append(
                    ClassificationResult(
                        custom_id=review.custom_id,
                        review_text=review.text,
                        sentiment=None,
                        confidence=None,
                        reason=None,
                        raw_content=row,
                        error=f"结果解析失败: {exc}",
                    )
                )
        elif err_row is not None:
            final.append(
                ClassificationResult(
                    custom_id=review.custom_id,
                    review_text=review.text,
                    sentiment=None,
                    confidence=None,
                    reason=None,
                    raw_content=None,
                    error=json.dumps(err_row, ensure_ascii=False),
                )
            )
        else:
            final.append(
                ClassificationResult(
                    custom_id=review.custom_id,
                    review_text=review.text,
                    sentiment=None,
                    confidence=None,
                    reason=None,
                    raw_content=None,
                    error="未在输出或错误文件中找到对应 custom_id（任务可能未完全完成）",
                )
            )
    return final


def write_results_csv(results: list[ClassificationResult], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["custom_id", "review", "sentiment", "confidence", "reason", "error"])
        for r in results:
            writer.writerow(
                [r.custom_id, r.review_text, r.sentiment or "", r.confidence or "", r.reason or "", r.error or ""]
            )
    print(f"[6/6] 结果已写入 {out_path}")

    ok = sum(1 for r in results if r.sentiment and not r.error)
    failed = len(results) - ok
    print(f"    成功分类 {ok} 条，失败/异常 {failed} 条（共 {len(results)} 条）")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_batch_sentiment_pipeline(
    reviews: list[Review],
    work_dir: str,
    out_csv: str,
) -> None:
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    requests_path = os.path.join(work_dir, "batch_requests.jsonl")
    output_path = os.path.join(work_dir, "batch_output.jsonl")
    error_path = os.path.join(work_dir, "batch_errors.jsonl")

    # 1. 构建请求文件
    write_batch_jsonl(reviews, requests_path)

    # 2. 上传文件（purpose=batch）
    input_file_id = upload_batch_file(requests_path)

    # 3. 创建 Batch 任务
    batch_id = create_batch(input_file_id, description=f"{len(reviews)} 条客户评论情感分类")

    # 4. 轮询状态直到终态
    batch = poll_batch(batch_id)
    status = batch.get("status")
    print(f"[5/6] Batch 任务结束，最终状态：{status}")

    if status != "completed":
        print(
            f"    警告：任务未以 completed 结束（status={status}）。"
            "已完成的请求仍可能已产生结果/费用，脚本会尝试下载现有的 output/error 文件。"
        )

    output_rows: dict[str, dict] = {}
    error_rows: dict[str, dict] = {}

    if batch.get("output_file_id"):
        download_file_content(batch["output_file_id"], output_path)
        output_rows = parse_output_jsonl(output_path)
        print(f"    已下载成功结果文件：{output_path}（{len(output_rows)} 条）")

    if batch.get("error_file_id"):
        download_file_content(batch["error_file_id"], error_path)
        error_rows = parse_output_jsonl(error_path)
        print(f"    已下载失败结果文件：{error_path}（{len(error_rows)} 条）")

    # 5. 汇总、落盘
    results = build_final_results(reviews, output_rows, error_rows)
    write_results_csv(results, out_csv)


def main() -> None:
    parser = argparse.ArgumentParser(description="客户评论情感分类 Batch 批处理脚本（bigmodel.cn）")
    parser.add_argument("--input", help="评论 CSV 文件路径，需包含 'review' 列")
    parser.add_argument("--text-column", default="review", help="CSV 中评论文本所在列名，默认 review")
    parser.add_argument("--demo", action="store_true", help="使用内置演示数据代替 --input")
    parser.add_argument("--demo-n", type=int, default=20, help="--demo 模式下生成多少条演示评论")
    parser.add_argument("--work-dir", default="batch_work", help="中间文件（jsonl）存放目录")
    parser.add_argument("--out", default="sentiment_results.csv", help="最终结果 CSV 输出路径")
    args = parser.parse_args()

    if not args.demo and not args.input:
        parser.error("请指定 --input reviews.csv 或使用 --demo 跑演示数据")

    reviews = demo_reviews(args.demo_n) if args.demo else load_reviews_from_csv(args.input, args.text_column)
    print(f"共读取到 {len(reviews)} 条评论，模型 = {MODEL}")

    run_batch_sentiment_pipeline(reviews, work_dir=args.work_dir, out_csv=args.out)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - 顶层兜底，打印清晰错误后以非零码退出
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
