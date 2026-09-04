#!/usr/bin/env python3
"""
Batch-summarise Markdown notes with Volcengine Ark **Agent Plan** quota.

    notes/*.md  ──►  doubao-seed-2.0-lite (Agent Plan, /api/plan/v3)  ──►  summaries/*.md

Every design choice below exists so that the run is paid from the Agent Plan
AFP quota and never from the pay-as-you-go balance.  See NOTES.md.

Usage:
    export ARK_AGENT_PLAN_API_KEY="..."        # Agent Plan 专属 Key（不是方舟 API Key）
    python summarize_notes.py                  # notes/ -> summaries/
    python summarize_notes.py --notes-dir notes --out-dir summaries --workers 2
    python summarize_notes.py --dry-run        # 只列出将要处理的文件，不调用 API
    python summarize_notes.py --force          # 重新生成已存在的摘要
    python summarize_notes.py --budget-afp 500 # 本次运行估算消耗超过 500 AFP 时停止
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖：pip install -r requirements.txt  (openai>=1.0)")

# --------------------------------------------------------------------------- #
# Agent Plan constants — do NOT "fix" these to /api/v3 or ARK_API_KEY.
# --------------------------------------------------------------------------- #

# Agent Plan 的 OpenAI 协议入口。/api/v3 是标准后付费入口，会从余额扣钱。
AGENT_PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"

# Agent Plan 专属 Key 的环境变量名。方舟 API Key（ARK_API_KEY）在 /api/plan 下会 401。
PLAN_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
POSTPAID_KEY_ENV = "ARK_API_KEY"

# Plan 入口用小写、带点的 Model Name（不是带日期的 Model ID）。
MODEL_NAME = "doubao-seed-2.0-lite"
# 服务端把这个 Name 解析到某个日期版本并在响应 model 里回显（实测 2026-09-04 为
# doubao-seed-2-0-lite-260215）。我们只校验前缀，不依赖具体日期。
EXPECTED_MODEL_PREFIX = "doubao-seed-2-0-lite"

# AFP 抵扣系数（doubao-seed-2.0-lite：输入 0.5 / 输出 0.5，2026-09-01 起不再按长度分段）。
AFP_IN_COEF = 0.5
AFP_OUT_COEF = 0.5

# 输入保护：模型上下文 256k token，这里按字符保守截断，避免超长笔记撞上下文上限。
MAX_INPUT_CHARS = 120_000

# 三句话摘要不需要很多输出 token；思考已关闭，所以 max_tokens 只限制回答本身。
MAX_TOKENS = 512

SYSTEM_PROMPT = (
    "你是一个严谨的笔记摘要助手。用户会给你一篇 Markdown 笔记，"
    "请用恰好三句话概括其核心内容。要求：使用与笔记相同的语言；"
    "只输出这三句话本身，不要标题、编号、前言或 Markdown 标记；"
    "不要编造笔记中没有的信息。"
)

# 可重试的方舟错误码（限流 / 突增保护 / 服务端瞬时故障）。限流请求不计费，可放心重试。
RETRYABLE_CODE_PREFIXES = (
    "RateLimitExceeded",
    "ModelAccountRpmRateLimitExceeded",
    "ModelAccountTpmRateLimitExceeded",
    "APIAccountRpmRateLimitExceeded",
    "AccountRateLimitExceeded",
    "ServerOverloaded",
    "RequestBurstTooFast",
    "InternalServiceError",
)

# 一旦出现就应当停止整个批次的错误码：套餐额度耗尽 / 鉴权 / 订阅 / 模型不在套餐内。
# 这些错误重试没有意义，继续打只会浪费时间（且 QuotaExceeded 正是"没扣余额"的证据）。
FATAL_CODES = (
    "QuotaExceeded",
    "AuthenticationError",
    "InvalidSubscription",
    "InvalidAccountStatus",
    "UnsupportedModel",
)

log = logging.getLogger("summarize")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class BatchAbort(RuntimeError):
    """Raised when the whole batch must stop (quota exhausted, bad key, budget cap, ...).

    ``file_done`` is True when the current file's summary was already written
    (e.g. the AFP budget cap tripped *after* a successful, paid-for response).
    """

    def __init__(self, message: str, *, file_done: bool = False):
        super().__init__(message)
        self.file_done = file_done


def _error_code(exc: APIStatusError) -> str:
    """Extract Ark's ``error.code`` from an openai APIStatusError. Never parse ``message``."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            code = err.get("code")
            if isinstance(code, str):
                return code
    return ""


def _is_retryable(code: str, status: int) -> bool:
    if any(code.startswith(p) for p in RETRYABLE_CODE_PREFIXES):
        return True
    # Unknown 5xx with no code: treat as transient.
    return status >= 500 and not code


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


def build_client(timeout: float) -> OpenAI:
    api_key = os.environ.get(PLAN_KEY_ENV, "").strip()
    if not api_key:
        hint = ""
        if os.environ.get(POSTPAID_KEY_ENV):
            hint = (
                f"\n检测到 {POSTPAID_KEY_ENV} 已设置——那是方舟标准 API Key（后付费），"
                f"在 Agent Plan 入口会 401，本脚本故意不使用它。"
            )
        raise SystemExit(
            f"未设置环境变量 {PLAN_KEY_ENV}。\n"
            f"请到 Agent Plan 控制台 → 使用配置 → 第 3 步「配置专属API Key」复制专属 Key，"
            f"然后 export {PLAN_KEY_ENV}=...{hint}"
        )

    base_url = os.environ.get("ARK_AGENT_PLAN_BASE_URL", AGENT_PLAN_BASE_URL).rstrip("/")
    # Hard guard: whatever someone puts in the override, it must still be the Plan entry.
    if "/api/plan" not in base_url:
        raise SystemExit(
            f"Base URL {base_url!r} 不是 Agent Plan 入口（必须包含 /api/plan）。"
            f"/api/v3 会走后付费并从余额扣钱，拒绝启动。"
        )

    # max_retries=0: we implement our own retry so that QuotaExceeded (429) is NOT
    # retried blindly while genuine rate limits are.
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)


# --------------------------------------------------------------------------- #
# Usage / AFP accounting
# --------------------------------------------------------------------------- #


@dataclass
class UsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    files_ok: int = 0
    files_failed: int = 0
    files_skipped: int = 0

    @property
    def afp(self) -> float:
        return (self.prompt_tokens * AFP_IN_COEF + self.completion_tokens * AFP_OUT_COEF) / 10_000


class Budget:
    """Thread-safe running total; raises BatchAbort when an optional AFP cap is exceeded."""

    def __init__(self, cap_afp: Optional[float]):
        self.cap = cap_afp
        self.totals = UsageTotals()
        self._lock = threading.Lock()
        # Set once any fatal condition is seen; workers check it before sending a request,
        # so a QuotaExceeded / bad-key / budget stop does not let other threads keep firing.
        self.stop = threading.Event()

    def add(self, prompt: int, completion: int, reasoning: int) -> float:
        """Record usage of one successful file; returns the running AFP estimate."""
        with self._lock:
            self.totals.prompt_tokens += prompt
            self.totals.completion_tokens += completion
            self.totals.reasoning_tokens += reasoning
            self.totals.files_ok += 1
            return self.totals.afp

    def check(self, spent: float) -> None:
        """Call *after* the summary has been persisted, so paid-for output is never discarded."""
        if self.cap is not None and spent > self.cap:
            self.stop.set()
            raise BatchAbort(
                f"估算 AFP 消耗 {spent:.2f} 已超过 --budget-afp {self.cap}，停止批次。", file_done=True
            )

    def failed(self) -> None:
        with self._lock:
            self.totals.files_failed += 1

    def skipped(self) -> None:
        with self._lock:
            self.totals.files_skipped += 1


# --------------------------------------------------------------------------- #
# Core call
# --------------------------------------------------------------------------- #


@dataclass
class SummaryResult:
    text: str
    served_model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    finish_reason: str
    request_id: str


def summarize_text(
    client: OpenAI,
    note_text: str,
    *,
    request_id: str,
    max_attempts: int = 6,
) -> SummaryResult:
    if len(note_text) > MAX_INPUT_CHARS:
        log.warning("输入超过 %d 字符，已截断（request %s）", MAX_INPUT_CHARS, request_id)
        note_text = note_text[:MAX_INPUT_CHARS] + "\n\n[... 笔记过长，已截断 ...]"

    messages = [
        # NOTE: role must be system/user/assistant/tool. `developer` -> 400 InvalidParameter.
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请用三句话概括下面这篇笔记：\n\n{note_text}"},
    ]

    delay = 1.5
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=MAX_TOKENS,
                # 方舟私有字段走 extra_body。doubao-seed-2.0-lite 默认开思考；摘要不需要，
                # 关掉后 reasoning_tokens=0，AFP 消耗只剩输入 + 三句话输出。
                extra_body={"thinking": {"type": "disabled"}},
                # 自定义请求 ID，方便对照控制台用量明细 / 报工单。
                extra_headers={"X-Client-Request-Id": request_id},
            )
        except APIStatusError as e:
            code = _error_code(e)
            status = e.status_code
            if code in FATAL_CODES or status in (401, 403):
                raise BatchAbort(f"HTTP {status} {code or '(no code)'}: {e.message}") from e
            if _is_retryable(code, status) and attempt < max_attempts:
                sleep_for = delay + random.uniform(0, delay / 2)
                log.warning(
                    "HTTP %s %s，%.1fs 后重试（%d/%d）", status, code or "?", sleep_for, attempt, max_attempts
                )
                time.sleep(sleep_for)
                delay = min(delay * 2, 30)
                continue
            raise  # 400 参数类等：不重试，交给上层记为该文件失败
        except (APIConnectionError, APITimeoutError) as e:
            if attempt < max_attempts:
                sleep_for = delay + random.uniform(0, delay / 2)
                log.warning("网络错误 %s，%.1fs 后重试（%d/%d）", type(e).__name__, sleep_for, attempt, max_attempts)
                time.sleep(sleep_for)
                delay = min(delay * 2, 30)
                continue
            raise

        served_model = resp.model or ""
        if not served_model.startswith(EXPECTED_MODEL_PREFIX):
            # Plan 入口会静默改写 model；如果回显的不是 2.0-lite 系列，说明被路由到了
            # 别的（可能系数更高的）模型，立刻停下来让人检查，而不是继续烧 AFP。
            raise BatchAbort(
                f"响应 model={served_model!r}，不是预期的 {EXPECTED_MODEL_PREFIX}*；"
                f"为避免按更高系数扣 AFP 已停止。"
            )

        choice = resp.choices[0]
        content = (choice.message.content or "").strip()
        usage = resp.usage
        p = usage.prompt_tokens if usage else 0
        c = usage.completion_tokens if usage else 0
        r = 0
        if usage and getattr(usage, "completion_tokens_details", None):
            r = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0
        return SummaryResult(
            text=content,
            served_model=served_model,
            prompt_tokens=p,
            completion_tokens=c,
            reasoning_tokens=r,
            finish_reason=choice.finish_reason or "",
            request_id=request_id,
        )

    raise RuntimeError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------- #
# File orchestration
# --------------------------------------------------------------------------- #


def needs_summary(src: Path, dst: Path, force: bool) -> bool:
    if force or not dst.exists():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def process_file(client: OpenAI, src: Path, dst: Path, budget: Budget) -> None:
    if budget.stop.is_set():
        budget.skipped()
        return
    text = src.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        log.info("跳过空文件 %s", src)
        budget.skipped()
        return

    request_id = f"notes-{src.stem[:40]}-{uuid.uuid4().hex[:8]}"
    try:
        result = summarize_text(client, text, request_id=request_id)
    except BatchAbort:
        budget.stop.set()
        raise

    if result.finish_reason == "length":
        log.warning("%s: finish_reason=length，摘要可能被截断（max_tokens=%d）", src.name, MAX_TOKENS)
    if not result.text:
        raise RuntimeError(f"{src.name}: 模型返回空内容（finish_reason={result.finish_reason}）")
    if result.reasoning_tokens:
        log.warning("%s: reasoning_tokens=%d，思考未被关闭？请检查", src.name, result.reasoning_tokens)

    file_afp = (result.prompt_tokens * AFP_IN_COEF + result.completion_tokens * AFP_OUT_COEF) / 10_000
    spent = budget.add(result.prompt_tokens, result.completion_tokens, result.reasoning_tokens)

    header = (
        f"<!-- source: {src.as_posix()} | model: {result.served_model} | "
        f"tokens: {result.prompt_tokens}+{result.completion_tokens} | afp≈{file_afp:.3f} | "
        f"request: {result.request_id} -->\n\n"
    )
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(header + result.text + "\n", encoding="utf-8")
    tmp.replace(dst)  # atomic: never leave a half-written summary behind
    log.info(
        "✓ %s -> %s  (%d+%d tok, ≈%.3f AFP, 累计 ≈%.2f AFP)",
        src.name, dst.name, result.prompt_tokens, result.completion_tokens, file_afp, spent,
    )
    budget.check(spent)


def collect_jobs(notes_dir: Path, out_dir: Path, force: bool) -> tuple[list[tuple[Path, Path]], int]:
    jobs: list[tuple[Path, Path]] = []
    skipped = 0
    for src in sorted(notes_dir.rglob("*.md")):
        if not src.is_file():
            continue
        rel = src.relative_to(notes_dir)
        dst = out_dir / rel
        if needs_summary(src, dst, force):
            jobs.append((src, dst))
        else:
            skipped += 1
    return jobs, skipped


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--notes-dir", default="notes", type=Path)
    ap.add_argument("--out-dir", default="summaries", type=Path)
    ap.add_argument("--workers", default=2, type=int,
                    help="并发数（默认 2；Medium 套餐官方建议 1–2 个项目同时使用，别开太大）")
    ap.add_argument("--timeout", default=120.0, type=float, help="单请求超时秒数（思考已关闭，120s 足够）")
    ap.add_argument("--budget-afp", default=None, type=float,
                    help="本次运行的 AFP 上限（估算值），超过即停止；不设则不限")
    ap.add_argument("--force", action="store_true", help="即使摘要已存在也重新生成")
    ap.add_argument("--dry-run", action="store_true", help="只列出将要处理的文件，不调用 API")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.notes_dir.is_dir():
        log.error("笔记目录不存在：%s", args.notes_dir)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)

    jobs, already = collect_jobs(args.notes_dir, args.out_dir, args.force)
    log.info("待处理 %d 个文件，已存在且未过期 %d 个（用 --force 重新生成）", len(jobs), already)
    if not jobs:
        return 0

    if args.dry_run:
        for src, dst in jobs:
            print(f"{src}  ->  {dst}")
        total_chars = sum(len(src.read_text(encoding='utf-8', errors='replace')) for src, _ in jobs)
        # 粗估：中文约 1 字 ≈ 1 token，英文约 4 字符 ≈ 1 token；这里按 1 字符 ≈ 0.7 token 取中值。
        est_prompt = int(total_chars * 0.7) + 200 * len(jobs)
        est_completion = 150 * len(jobs)
        print(f"\n[dry-run] 约 {total_chars} 字符 → 粗估 {est_prompt}+{est_completion} token ≈ "
              f"{(est_prompt * AFP_IN_COEF + est_completion * AFP_OUT_COEF) / 10_000:.1f} AFP "
              f"（{MODEL_NAME} 系数 {AFP_IN_COEF}/{AFP_OUT_COEF}，思考关闭）")
        return 0

    client = build_client(timeout=args.timeout)
    budget = Budget(args.budget_afp)
    log.info("Base URL: %s | model: %s | key: %s | workers: %d",
             client.base_url, MODEL_NAME, PLAN_KEY_ENV, max(1, args.workers))

    abort: Optional[BaseException] = None
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {}
        for src, dst in jobs:
            dst.parent.mkdir(parents=True, exist_ok=True)
            futures[pool.submit(process_file, client, src, dst, budget)] = src
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                fut.result()
            except BatchAbort as e:
                if abort is None:
                    abort = e
                    log.error("停止批次：%s", e)
                    # Cancel everything not yet started; in-flight requests finish naturally.
                    for f in futures:
                        f.cancel()
                if not e.file_done:
                    budget.failed()
            except Exception as e:  # noqa: BLE001 — per-file failure, keep going
                budget.failed()
                log.error("✗ %s: %s", src.name, e)

    t = budget.totals
    log.info(
        "完成：成功 %d，失败 %d，跳过 %d | tokens %d+%d (reasoning %d) | 估算消耗 ≈ %.2f AFP",
        t.files_ok, t.files_failed, t.files_skipped, t.prompt_tokens, t.completion_tokens,
        t.reasoning_tokens, t.afp,
    )
    if abort is not None:
        log.error("批次因致命错误提前结束；修复后重跑即可，已生成的摘要会被跳过。")
        return 1
    return 0 if t.files_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
