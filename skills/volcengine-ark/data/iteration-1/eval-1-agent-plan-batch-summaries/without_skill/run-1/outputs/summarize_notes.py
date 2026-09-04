#!/usr/bin/env python3
"""
Batch-summarize Markdown notes with 火山方舟 (Volcengine Ark) using an
Agent Plan (套餐) quota instead of pay-as-you-go balance.

    notes/*.md  --(doubao-seed-2.0-lite, 3-sentence summary)-->  summaries/*.md

Usage:
    export ARK_API_KEY="..."               # key shown on the Agent Plan page
    export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"  # plan endpoint
    python summarize_notes.py --notes notes --out summaries

Billing safety (the whole point of this script):
  * Requests go to the *plan* endpoint (ARK_BASE_URL), never the standard
    pay-as-you-go endpoint ".../api/v3". If ARK_BASE_URL points at the
    standard endpoint the script refuses to start unless --allow-postpaid
    is passed explicitly.
  * The model must be one of the plan-eligible models you declare in
    ARK_PLAN_MODELS (comma separated). Default list contains only the model
    this task needs. A model outside the plan silently bills to balance on
    some endpoints, so we fail closed here too.
  * Every response's token usage is appended to summaries/_usage.jsonl so
    you can reconcile against the plan usage shown in the console.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import logging
import os
import random
import re
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

try:
    from openai import (
        OpenAI,
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        PermissionDeniedError,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency: pip install -r requirements.txt  (needs `openai>=1.40`)\n"
    )
    sys.exit(2)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Region host for Ark (mainland). Plans are bound to this host.
ARK_HOST = "https://ark.cn-beijing.volces.com"

# Pay-as-you-go endpoint. Traffic here is billed to the postpaid balance.
POSTPAID_BASE_URL = f"{ARK_HOST}/api/v3"

# Plan endpoint. Coding Plan launched with `/api/coding/v3`; the Agent Plan
# page in the console shows the exact Base URL for your subscription. We do
# NOT hard-code a silent fallback to the postpaid endpoint on purpose.
DEFAULT_PLAN_BASE_URL = f"{ARK_HOST}/api/coding/v3"

DEFAULT_MODEL = "doubao-seed-2.0-lite"

# Rough safety cap on input size. doubao-seed-2.0 models have a 256k context,
# but a 3-sentence summary of a note never needs that much, and plan quotas
# are usually counted in tokens/requests. ~1 CJK char ~= 1 token; ~4 ASCII
# chars ~= 1 token. 60k chars is far below the model limit either way.
DEFAULT_MAX_INPUT_CHARS = 60_000

USAGE_LEDGER_NAME = "_usage.jsonl"

SYSTEM_PROMPT = (
    "你是一名严谨的笔记摘要助手。"
    "阅读用户提供的 Markdown 笔记，用与笔记相同的主要语言写出恰好三句话的摘要。"
    "要求：只输出这三句话，写成一个自然段；不要标题、不要列表、不要编号、不要 Markdown 标记、"
    "不要任何前言或结尾说明；不要编造笔记中没有的信息。"
)

USER_PROMPT_TEMPLATE = (
    "文件名：{filename}\n\n"
    "请为下面这篇笔记生成三句话摘要。\n\n"
    "<note>\n{content}\n</note>"
)

log = logging.getLogger("summarize")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    plan_models: tuple[str, ...]
    notes_dir: Path
    out_dir: Path
    concurrency: int
    max_input_chars: int
    max_output_tokens: int
    temperature: float
    timeout_s: float
    max_retries: int
    force: bool
    dry_run: bool
    disable_thinking: bool


class ConfigError(RuntimeError):
    pass


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def load_settings(argv: Optional[list[str]] = None) -> Settings:
    p = argparse.ArgumentParser(
        description="Summarize notes/*.md with Ark Agent Plan quota.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--notes", default=_env("NOTES_DIR", "notes"), help="input directory of .md files")
    p.add_argument("--out", default=_env("SUMMARIES_DIR", "summaries"), help="output directory")
    p.add_argument("--model", default=_env("ARK_MODEL", DEFAULT_MODEL))
    p.add_argument("--concurrency", type=int, default=int(_env("ARK_CONCURRENCY", "3")),
                   help="parallel requests; keep small to stay under plan RPM")
    p.add_argument("--max-input-chars", type=int, default=int(_env("MAX_INPUT_CHARS", str(DEFAULT_MAX_INPUT_CHARS))))
    p.add_argument("--max-output-tokens", type=int, default=400)
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--timeout", type=float, default=120.0, help="per-request timeout seconds")
    p.add_argument("--max-retries", type=int, default=5)
    p.add_argument("--force", action="store_true", help="re-generate even if summary exists")
    p.add_argument("--dry-run", action="store_true", help="list work, make no API calls")
    p.add_argument("--keep-thinking", action="store_true",
                   help="do not disable the model's thinking mode (costs more quota)")
    p.add_argument("--allow-postpaid", action="store_true",
                   help="DANGER: permit the pay-as-you-go endpoint (bills your balance)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = _env("ARK_API_KEY")
    if not api_key:
        raise ConfigError(
            "ARK_API_KEY is not set. Copy the key from the Agent Plan page in the Ark console "
            "and `export ARK_API_KEY=...`. The key is never read from files or CLI args."
        )
    if api_key.lower().startswith(("bearer ", "sk-ant", "sk-proj")):
        raise ConfigError("ARK_API_KEY does not look like an Ark key (do not include 'Bearer ').")

    base_url = (_env("ARK_BASE_URL", DEFAULT_PLAN_BASE_URL) or "").rstrip("/")
    if not base_url.startswith("https://"):
        raise ConfigError("ARK_BASE_URL must be https://")
    if base_url == POSTPAID_BASE_URL and not args.allow_postpaid:
        raise ConfigError(
            f"ARK_BASE_URL={base_url} is the pay-as-you-go endpoint; requests there are billed to "
            "your postpaid balance, not the Agent Plan. Set ARK_BASE_URL to the plan Base URL shown "
            f"on the Agent Plan page (e.g. {DEFAULT_PLAN_BASE_URL}), or pass --allow-postpaid if you "
            "really mean it."
        )
    if not base_url.startswith(ARK_HOST):
        log.warning("ARK_BASE_URL host is not %s — make sure this is really an Ark plan endpoint.", ARK_HOST)

    plan_models_raw = _env("ARK_PLAN_MODELS", DEFAULT_MODEL) or ""
    plan_models = tuple(m.strip() for m in plan_models_raw.split(",") if m.strip())
    if args.model not in plan_models and not args.allow_postpaid:
        raise ConfigError(
            f"model '{args.model}' is not in ARK_PLAN_MODELS={plan_models}. Only models included in "
            "your Agent Plan consume plan quota; anything else may bill your balance. Add it to "
            "ARK_PLAN_MODELS after confirming it on the plan page."
        )
    if re.fullmatch(r"ep-[0-9a-z-]+", args.model):
        log.warning(
            "model '%s' looks like a custom endpoint (ep-...). Custom endpoints are billed per "
            "endpoint, not via plans — double-check before continuing.", args.model
        )

    if args.concurrency < 1:
        raise ConfigError("--concurrency must be >= 1")

    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=args.model,
        plan_models=plan_models,
        notes_dir=Path(args.notes).expanduser(),
        out_dir=Path(args.out).expanduser(),
        concurrency=args.concurrency,
        max_input_chars=args.max_input_chars,
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
        timeout_s=args.timeout,
        max_retries=args.max_retries,
        force=args.force,
        dry_run=args.dry_run,
        disable_thinking=not args.keep_thinking,
    )


# --------------------------------------------------------------------------- #
# File handling
# --------------------------------------------------------------------------- #


def iter_notes(notes_dir: Path) -> Iterable[Path]:
    if not notes_dir.is_dir():
        raise ConfigError(f"notes dir not found: {notes_dir}")
    for path in sorted(notes_dir.rglob("*.md")):
        if path.name.startswith(".") or not path.is_file():
            continue
        yield path


def output_path_for(note: Path, notes_dir: Path, out_dir: Path) -> Path:
    # Mirror sub-directories so notes/a/b.md -> summaries/a/b.md
    return out_dir / note.relative_to(notes_dir)


def read_note(path: Path, max_chars: int) -> tuple[str, bool]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gb18030", errors="replace")
        log.warning("%s: not UTF-8, decoded as GB18030 with replacement", path)
    text = text.strip()
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... 内容过长，已截断 ...]"
        truncated = True
    return text, truncated


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Model call
# --------------------------------------------------------------------------- #

_SENTENCE_END = re.compile(r"[。！？!?\.]+[”\"')）]*")


def count_sentences(text: str) -> int:
    return len([m for m in _SENTENCE_END.finditer(text)])


def clean_summary(text: str) -> str:
    text = text.strip()
    # Strip a leading "摘要：" / "Summary:" style label if the model adds one.
    text = re.sub(r"^\s*(摘要|总结|Summary)\s*[:：]\s*", "", text, flags=re.I)
    # Collapse to one paragraph.
    text = re.sub(r"\s*\n+\s*", " ", text)
    # Strip stray markdown bullets/emphasis.
    text = re.sub(r"^[\-\*\d\.\s]+", "", text)
    text = text.replace("**", "")
    return text.strip()


class Summarizer:
    def __init__(self, s: Settings):
        self.s = s
        # Retries are handled by our own loop so that we can back off on 429
        # with jitter; the SDK's built-in retry is disabled to avoid doubling.
        self.client = OpenAI(
            api_key=s.api_key,
            base_url=s.base_url,
            timeout=s.timeout_s,
            max_retries=0,
        )

    def _extra_body(self) -> dict:
        extra: dict = {}
        if self.s.disable_thinking:
            # doubao-seed-2.0 family supports a `thinking` switch. Disabling it
            # cuts latency and output-token consumption of the plan quota; a
            # three-sentence summary does not need reasoning.
            extra["thinking"] = {"type": "disabled"}
        return extra

    def summarize(self, filename: str, content: str) -> tuple[str, dict]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(filename=filename, content=content)},
        ]
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.client.chat.completions.create(
                    model=self.s.model,
                    messages=messages,
                    temperature=self.s.temperature,
                    max_tokens=self.s.max_output_tokens,
                    extra_body=self._extra_body(),
                )
                break
            except (AuthenticationError, PermissionDeniedError) as e:
                raise RuntimeError(
                    f"auth failed against {self.s.base_url}: {e}. Check that ARK_API_KEY is the key "
                    "shown on the Agent Plan page and that the plan is active."
                ) from e
            except NotFoundError as e:
                raise RuntimeError(
                    f"model '{self.s.model}' not found on {self.s.base_url}: {e}. The model may not be "
                    "part of your plan, or the Base URL is wrong."
                ) from e
            except BadRequestError as e:
                # Typically a parameter the endpoint doesn't accept (e.g. `thinking`
                # on a model that lacks it). Retry once without extra_body.
                if self.s.disable_thinking and attempt == 1 and "thinking" in str(e).lower():
                    log.warning("%s: endpoint rejected `thinking` param, retrying without it", filename)
                    self.s = Settings(**{**asdict(self.s), "disable_thinking": False})
                    continue
                raise RuntimeError(f"bad request for {filename}: {e}") from e
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt > self.s.max_retries:
                    raise RuntimeError(f"{filename}: gave up after {attempt - 1} retries: {e}") from e
                delay = self._backoff(attempt, getattr(e, "response", None))
                log.warning("%s: %s — retry %d/%d in %.1fs", filename, type(e).__name__, attempt,
                            self.s.max_retries, delay)
                time.sleep(delay)
            except APIStatusError as e:
                if e.status_code >= 500 and attempt <= self.s.max_retries:
                    delay = self._backoff(attempt, e.response)
                    log.warning("%s: HTTP %s — retry %d/%d in %.1fs", filename, e.status_code, attempt,
                                self.s.max_retries, delay)
                    time.sleep(delay)
                    continue
                if e.status_code in (402, 403, 429) and "quota" in str(e).lower():
                    raise RuntimeError(
                        f"plan quota appears exhausted ({e.status_code}): {e}. Stopping so nothing falls "
                        "through to postpaid billing."
                    ) from e
                raise RuntimeError(f"{filename}: HTTP {e.status_code}: {e}") from e

        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        if not text:
            raise RuntimeError(f"{filename}: empty completion (finish_reason={choice.finish_reason})")
        if choice.finish_reason == "length":
            log.warning("%s: output hit max_tokens; consider raising --max-output-tokens", filename)

        usage = {}
        if resp.usage is not None:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return text, usage

    @staticmethod
    def _backoff(attempt: int, response) -> float:
        # Honour Retry-After when the server sends one.
        if response is not None:
            ra = response.headers.get("retry-after") if hasattr(response, "headers") else None
            if ra:
                try:
                    return min(float(ra), 60.0)
                except ValueError:
                    pass
        base = min(2 ** attempt, 30)
        return base + random.uniform(0, 1.0)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    note: str
    status: str  # ok | skipped | failed
    detail: str = ""
    usage: Optional[dict] = None


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def record(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def process_one(note: Path, s: Settings, summarizer: Optional[Summarizer], ledger: Ledger) -> Result:
    out = output_path_for(note, s.notes_dir, s.out_dir)
    rel = str(note.relative_to(s.notes_dir))

    if out.exists() and not s.force:
        return Result(rel, "skipped", "summary exists (use --force to redo)")

    try:
        content, truncated = read_note(note, s.max_input_chars)
    except OSError as e:
        return Result(rel, "failed", f"read error: {e}")
    if not content:
        return Result(rel, "skipped", "empty file")

    if s.dry_run or summarizer is None:
        return Result(rel, "ok", f"dry-run ({len(content)} chars{', truncated' if truncated else ''})")

    try:
        raw, usage = summarizer.summarize(note.name, content)
    except RuntimeError as e:
        return Result(rel, "failed", str(e))

    summary = clean_summary(raw)
    n = count_sentences(summary)
    if n != 3:
        log.warning("%s: model returned %d sentences instead of 3; saving anyway", rel, n)

    body = (
        f"# {note.stem}\n\n"
        f"{summary}\n\n"
        f"<!-- source: {rel} | model: {s.model} | "
        f"generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        f"| tokens: {usage.get('total_tokens', '?')}{' | input truncated' if truncated else ''} -->\n"
    )
    atomic_write(out, body)
    ledger.record({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": rel,
        "model": s.model,
        "base_url": s.base_url,
        "sentences": n,
        "truncated": truncated,
        **usage,
    })
    return Result(rel, "ok", f"{usage.get('total_tokens', '?')} tokens", usage)


def main(argv: Optional[list[str]] = None) -> int:
    try:
        s = load_settings(argv)
    except ConfigError as e:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
        log.error("%s", e)
        return 2

    log.info("endpoint : %s", s.base_url)
    log.info("model    : %s  (plan models: %s)", s.model, ", ".join(s.plan_models))
    log.info("key      : %s…%s", s.api_key[:4], s.api_key[-4:])  # never log the full key
    log.info("thinking : %s", "disabled" if s.disable_thinking else "model default")
    log.info("notes    : %s  ->  %s", s.notes_dir, s.out_dir)

    try:
        notes = list(iter_notes(s.notes_dir))
    except ConfigError as e:
        log.error("%s", e)
        return 2
    if not notes:
        log.warning("no .md files under %s; nothing to do", s.notes_dir)
        return 0
    log.info("found %d note(s)", len(notes))

    s.out_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(s.out_dir / USAGE_LEDGER_NAME)
    summarizer = None if s.dry_run else Summarizer(s)

    results: list[Result] = []
    with cf.ThreadPoolExecutor(max_workers=s.concurrency) as pool:
        futures = {pool.submit(process_one, n, s, summarizer, ledger): n for n in notes}
        for fut in cf.as_completed(futures):
            r = fut.result()
            results.append(r)
            level = logging.INFO if r.status != "failed" else logging.ERROR
            log.log(level, "[%s] %s — %s", r.status.upper(), r.note, r.detail)

    ok = sum(r.status == "ok" for r in results)
    skipped = sum(r.status == "skipped" for r in results)
    failed = sum(r.status == "failed" for r in results)
    total_tokens = sum((r.usage or {}).get("total_tokens", 0) for r in results)
    log.info("done: %d ok, %d skipped, %d failed, %d tokens used%s",
             ok, skipped, failed, total_tokens, " (dry-run)" if s.dry_run else "")
    if failed:
        log.info("re-run the same command to retry only the failed files (existing summaries are skipped)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
