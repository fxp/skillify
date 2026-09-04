#!/usr/bin/env python3
"""
Compare code reviews from two Volcengine Ark (火山方舟) models — kimi-k3 and glm-5.3.

Both models receive the same code snippet and the same review prompt. Each response is
capped at roughly 300 output tokens. glm-5.3 is called with its thinking (chain-of-thought)
disabled so it returns a conclusion directly.

Usage:
    export ARK_API_KEY=...            # required
    python review_compare.py                       # reviews the built-in sample snippet
    python review_compare.py path/to/file.py       # reviews the given file
    python review_compare.py --max-tokens 300 --json out.json path/to/file.py

Optional environment variables:
    ARK_BASE_URL   API endpoint. Defaults to the Agent Plan (coding) endpoint; see NOTES.md.
    ARK_KIMI_MODEL model id for Kimi   (default: kimi-k3)
    ARK_GLM_MODEL  model id for GLM    (default: glm-5.3)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    from openai import APIError, OpenAI
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency: pip install 'openai>=1.40'")

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
DEFAULT_MAX_TOKENS = 300
REQUEST_TIMEOUT_S = 120

SYSTEM_PROMPT = (
    "You are a senior software engineer performing a concise code review. "
    "Reply in the same language as the user. Stay under ~200 words. "
    "Use this exact structure:\n"
    "1. Verdict (one line: approve / request changes)\n"
    "2. Top issues (at most 3 bullets, most severe first, each with a one-line fix)\n"
    "3. Minor nits (at most 2 bullets, or 'none')\n"
    "Do not restate the code. Do not add closing remarks."
)

USER_PROMPT_TEMPLATE = (
    "请对下面这段 {language} 代码做 code review，直接给结论，不要展开推理过程。\n\n"
    "```{language}\n{code}\n```"
)

SAMPLE_CODE = '''\
import os

def load_users(path):
    f = open(path)
    data = f.read()
    users = eval(data)
    result = []
    for i in range(len(users)):
        if users[i]["active"] == True:
            result.append(users[i]["name"].lower())
    return result

def find_user(users, name):
    for u in users:
        if u == name:
            return True
    return False

def save_report(users, out_dir):
    os.system("mkdir " + out_dir)
    with open(out_dir + "/report.txt", "w") as f:
        for u in users:
            f.write(u + "\\n")
'''


@dataclass(frozen=True)
class ModelSpec:
    """How to call one model."""

    label: str
    model: str
    thinking_disabled: bool
    # Extra request fields that the OpenAI SDK does not know about; passed via extra_body.
    extra_body: dict[str, Any] = field(default_factory=dict)


def build_specs() -> list[ModelSpec]:
    kimi_model = os.environ.get("ARK_KIMI_MODEL", "kimi-k3")
    glm_model = os.environ.get("ARK_GLM_MODEL", "glm-5.3")
    return [
        # Kimi: default reasoning behaviour; output length is bounded by max_tokens.
        ModelSpec(label="Kimi K3", model=kimi_model, thinking_disabled=False),
        # GLM: explicitly turn off chain-of-thought so the whole budget goes to the answer.
        ModelSpec(
            label="GLM 5.3",
            model=glm_model,
            thinking_disabled=True,
            extra_body={"thinking": {"type": "disabled"}},
        ),
    ]


# --------------------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------------------


@dataclass
class ReviewResult:
    label: str
    model: str
    thinking_disabled: bool
    ok: bool
    content: str = ""
    reasoning_content: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_s: float = 0.0
    error: str | None = None


# --------------------------------------------------------------------------------------
# API call
# --------------------------------------------------------------------------------------


def make_client() -> OpenAI:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        sys.exit(
            "ARK_API_KEY is not set. Export your Volcengine Ark API key, e.g.\n"
            "  export ARK_API_KEY=your_key_here"
        )
    base_url = os.environ.get("ARK_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_S, max_retries=2)


def run_review(client: OpenAI, spec: ModelSpec, code: str, language: str, max_tokens: int) -> ReviewResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(language=language, code=code)},
    ]
    result = ReviewResult(
        label=spec.label, model=spec.model, thinking_disabled=spec.thinking_disabled, ok=False
    )
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=spec.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
            extra_body=spec.extra_body or None,
        )
    except APIError as exc:
        result.latency_s = time.perf_counter() - started
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    except Exception as exc:  # network errors, timeouts, etc.
        result.latency_s = time.perf_counter() - started
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.latency_s = time.perf_counter() - started
    choice = resp.choices[0]
    msg = choice.message
    result.ok = True
    result.content = (msg.content or "").strip()
    # Ark returns chain-of-thought (when enabled) as a non-standard `reasoning_content` field.
    result.reasoning_content = getattr(msg, "reasoning_content", None)
    result.finish_reason = choice.finish_reason

    usage = resp.usage
    if usage is not None:
        result.prompt_tokens = usage.prompt_tokens
        result.completion_tokens = usage.completion_tokens
        details = getattr(usage, "completion_tokens_details", None)
        if details is not None:
            result.reasoning_tokens = getattr(details, "reasoning_tokens", None)
    return result


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------


def _fmt_int(v: int | None) -> str:
    return "-" if v is None else str(v)


def print_report(results: list[ReviewResult], max_tokens: int) -> None:
    bar = "=" * 78
    for r in results:
        print(bar)
        mode = "thinking: off" if r.thinking_disabled else "thinking: default"
        print(f"{r.label}  ({r.model}, {mode})")
        print(bar)
        if not r.ok:
            print(f"[ERROR] {r.error}\n")
            continue
        print(r.content or "(empty response)")
        if r.finish_reason == "length":
            print(f"\n[warn] output was cut at max_tokens={max_tokens}; consider raising it.")
        if r.reasoning_content:
            n = len(r.reasoning_content)
            print(f"\n[info] model also returned {n} chars of reasoning_content (not shown).")
        print()

    print(bar)
    print("Summary")
    print(bar)
    header = f"{'model':<10} {'ok':<4} {'prompt':>7} {'compl':>6} {'reason':>7} {'finish':<8} {'latency':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.label:<10} {'yes' if r.ok else 'no':<4} "
            f"{_fmt_int(r.prompt_tokens):>7} {_fmt_int(r.completion_tokens):>6} "
            f"{_fmt_int(r.reasoning_tokens):>7} {r.finish_reason or '-':<8} {r.latency_s:>7.1f}s"
        )


def detect_language(path: str | None) -> str:
    if not path:
        return "python"
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go",
        ".java": "java", ".rs": "rust", ".c": "c", ".cpp": "cpp", ".rb": "ruby",
        ".sh": "bash", ".kt": "kotlin", ".swift": "swift", ".php": "php",
    }.get(ext, "text")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare kimi-k3 vs glm-5.3 code reviews on Volcengine Ark.")
    p.add_argument("file", nargs="?", help="Source file to review (default: built-in sample).")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                   help=f"Per-model output cap (default {DEFAULT_MAX_TOKENS}).")
    p.add_argument("--language", help="Override language tag used in the prompt.")
    p.add_argument("--json", metavar="PATH", help="Also write full results as JSON to PATH.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                code = fh.read()
        except OSError as exc:
            sys.exit(f"Cannot read {args.file}: {exc}")
    else:
        code = SAMPLE_CODE
    language = args.language or detect_language(args.file)

    client = make_client()
    results = [run_review(client, spec, code, language, args.max_tokens) for spec in build_specs()]
    print_report(results, args.max_tokens)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in results], fh, ensure_ascii=False, indent=2)
        print(f"\nFull results written to {args.json}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
