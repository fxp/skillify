#!/usr/bin/env python3
"""
用火山方舟 Agent Plan 的 kimi-k3 与 glm-5.3 分别对同一段代码做 code review，并比较结果。

入口 / 鉴权（三套入口互不通用，见 volcengine-ark skill）:
  Base URL : https://ark.cn-beijing.volces.com/api/plan/v3      (Agent Plan, OpenAI 兼容协议)
  Key      : 环境变量 ARK_AGENT_PLAN_API_KEY                     (Agent Plan 专属 Key, 不是方舟 API Key)
  model    : 小写 Model Name  kimi-k3 / glm-5.3                  (不是带日期的 Model ID)

输出长度与思维链控制（均为 2026-09-04 在 Agent Plan Medium 档实测过的行为）:
  kimi-k3 : 默认开思考，且 `max_tokens` 把思维链算在内 —— max_tokens=64 时回答被截成空串
            (finish_reason=length)。因此这里只传 `max_completion_tokens`(回答 + 思维链总预算，
            与 max_tokens 互斥)，并在 prompt 里要求回答 ≤ 300 token；若仍被截空则加大预算重试一次。
  glm-5.3 : 默认开思考且不可关 —— `thinking: {"type":"disabled"}` 与 `reasoning_effort: "none"`
            都返回 400。实测唯一有效的"不要思维链"写法是 `reasoning_effort: "low"`
            (reasoning_tokens=0，无 reasoning_content)。回答上限用 max_completion_tokens=300。

用法:
  export ARK_AGENT_PLAN_API_KEY=...
  python code_review_compare.py                       # 用内置示例代码
  python code_review_compare.py --code-file foo.py    # 评审指定文件
  python code_review_compare.py --dry-run             # 不调 API，只打印将要发送的请求体
  python code_review_compare.py --json result.json    # 同时把结构化结果写到文件
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖: pip install 'openai>=1.40'")

# --------------------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------------------
AGENT_PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

# 期望的回答长度（token）。两个模型都在 prompt 里被要求 ≤ 这个数；硬上限见各模型配置。
TARGET_ANSWER_TOKENS = 300
# kimi-k3 的思维链预算：max_completion_tokens 覆盖"思维链 + 回答"，所以要给思维链留空间。
KIMI_REASONING_BUDGET = 1500
# kimi-k3 被截空时的重试上限（预算翻倍一次）。
KIMI_MAX_ATTEMPTS = 2

SYSTEM_PROMPT = (
    "你是一名资深代码评审员。请对用户给出的代码做 code review：指出 bug、安全隐患、性能与可维护性问题，"
    "按严重程度排序，每条一行，格式为「[级别] 位置：问题 → 建议」。"
    f"整体回答控制在 {TARGET_ANSWER_TOKENS} token 以内，不要复述代码，不要寒暄，直接给结论。"
)

DEFAULT_CODE = '''\
import sqlite3

def get_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = '" + username + "'")
    rows = cur.fetchall()
    result = []
    for r in rows:
        result.append(r)
    return result

def save_password(users, name, pwd):
    users[name] = pwd
    f = open("users.txt", "a")
    f.write(name + ":" + pwd + "\\n")
    return True
'''


# --------------------------------------------------------------------------------------
# 模型配置
# --------------------------------------------------------------------------------------
@dataclass
class ModelConfig:
    """一个模型在 Agent Plan 入口的调用参数。"""

    name: str                         # Plan 入口的小写 Model Name
    max_completion_tokens: int        # 回答 + 思维链总预算（不可与 max_tokens 同传）
    # 传给 chat.completions.create 的其他原生参数（reasoning_effort 是 openai SDK 原生 kwarg）
    native_params: Dict[str, Any] = field(default_factory=dict)
    # 方舟私有字段（如 thinking），需走 extra_body；这里两个模型都不需要，保留扩展位
    extra_body: Dict[str, Any] = field(default_factory=dict)
    # 被截空（finish_reason=length 且 content 为空）时允许的最大尝试次数
    max_attempts: int = 1
    note: str = ""


MODEL_CONFIGS: List[ModelConfig] = [
    ModelConfig(
        name="kimi-k3",
        # 思维链 + 回答一起算：给思维链 1500、回答 300。实测 max_tokens=64 会把回答截空，
        # 所以这里绝不传 max_tokens。
        max_completion_tokens=TARGET_ANSWER_TOKENS + KIMI_REASONING_BUDGET,
        max_attempts=KIMI_MAX_ATTEMPTS,
        note="保留默认思考；用 max_completion_tokens 限制总量，prompt 限制回答长度",
    ),
    ModelConfig(
        name="glm-5.3",
        # reasoning_effort=low 实测 reasoning_tokens=0，所以预算基本全给回答。
        max_completion_tokens=TARGET_ANSWER_TOKENS,
        native_params={"reasoning_effort": "low"},
        # 不要写 extra_body={"thinking": {"type": "disabled"}} —— glm-5.3 返回 400。
        note="glm-5.3 不支持 thinking.disabled / reasoning_effort=none(均 400)；用 reasoning_effort=low 实现无思维链",
    ),
]


# --------------------------------------------------------------------------------------
# 结果结构
# --------------------------------------------------------------------------------------
@dataclass
class ReviewResult:
    requested_model: str
    served_model: Optional[str] = None      # 响应里的 model 字段（Plan 入口可能改写版本）
    content: str = ""
    reasoning_content: Optional[str] = None
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    latency_s: Optional[float] = None
    attempts: int = 0
    request_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.content.strip())

    @property
    def answer_tokens(self) -> Optional[int]:
        """回答本身的 token（completion_tokens 减去思维链）。"""
        if self.completion_tokens is None:
            return None
        return self.completion_tokens - (self.reasoning_tokens or 0)


# --------------------------------------------------------------------------------------
# 调用
# --------------------------------------------------------------------------------------
def build_messages(code: str, language_hint: str) -> List[Dict[str, str]]:
    # 只用 system / user / assistant / tool 四种 role；Plan 入口对 `developer` 返回 400。
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请评审以下代码：\n```{language_hint}\n{code}\n```"},
    ]


def build_request(cfg: ModelConfig, messages: List[Dict[str, str]], budget: int) -> Dict[str, Any]:
    """组装 chat.completions.create 的 kwargs（也用于 --dry-run 展示）。"""
    req: Dict[str, Any] = {
        "model": cfg.name,
        "messages": messages,
        "max_completion_tokens": budget,   # 绝不与 max_tokens 同传
        "temperature": 0.2,                # code review 要稳定，降低随机性
        **cfg.native_params,
    }
    if cfg.extra_body:
        req["extra_body"] = dict(cfg.extra_body)
    return req


def _error_summary(exc: Exception) -> str:
    """把 openai 异常压成一行：优先用方舟的 error.code（不要解析 message 做判断）。"""
    if isinstance(exc, APIStatusError):
        code = msg = None
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                code, msg = err.get("code"), err.get("message")
        rid = None
        try:
            rid = exc.response.headers.get("x-request-id")
        except Exception:  # noqa: BLE001
            pass
        return f"HTTP {exc.status_code} code={code} message={msg} request_id={rid}"
    if isinstance(exc, APITimeoutError):
        return "请求超时（思考模型可适当加大 --timeout）"
    if isinstance(exc, APIConnectionError):
        return f"连接失败: {exc}"
    return f"{type(exc).__name__}: {exc}"


def review_with_model(client: OpenAI, cfg: ModelConfig, messages: List[Dict[str, str]]) -> ReviewResult:
    result = ReviewResult(requested_model=cfg.name)
    budget = cfg.max_completion_tokens

    for attempt in range(1, cfg.max_attempts + 1):
        result.attempts = attempt
        req = build_request(cfg, messages, budget)
        t0 = time.perf_counter()
        try:
            raw = client.chat.completions.with_raw_response.create(**req)
        except Exception as exc:  # noqa: BLE001 —— 每个模型独立失败，不影响另一个
            result.error = _error_summary(exc)
            result.latency_s = round(time.perf_counter() - t0, 2)
            return result

        result.latency_s = round(time.perf_counter() - t0, 2)
        result.request_id = raw.headers.get("x-request-id")
        resp = raw.parse()

        choice = resp.choices[0]
        msg = choice.message
        result.served_model = resp.model
        result.finish_reason = choice.finish_reason
        result.content = (msg.content or "").strip()
        # reasoning_content 是方舟私有字段，不在 OpenAI SDK 的类型里，用 getattr 取
        result.reasoning_content = getattr(msg, "reasoning_content", None)
        if resp.usage:
            result.prompt_tokens = resp.usage.prompt_tokens
            result.completion_tokens = resp.usage.completion_tokens
            details = getattr(resp.usage, "completion_tokens_details", None)
            result.reasoning_tokens = getattr(details, "reasoning_tokens", None) if details else None

        truncated_empty = choice.finish_reason == "length" and not result.content
        if truncated_empty and attempt < cfg.max_attempts:
            # kimi-k3 的已知形态：思维链吃光预算、回答为空。预算翻倍再试一次。
            budget *= 2
            print(
                f"[{cfg.name}] 第 {attempt} 次被截空 (finish_reason=length, reasoning_tokens="
                f"{result.reasoning_tokens})，max_completion_tokens 提到 {budget} 重试…",
                file=sys.stderr,
            )
            continue
        if truncated_empty:
            result.error = (
                f"finish_reason=length 且回答为空（思维链 {result.reasoning_tokens} token 吃光了 "
                f"max_completion_tokens={budget}）；请加大 KIMI_REASONING_BUDGET"
            )
        return result

    return result  # pragma: no cover


# --------------------------------------------------------------------------------------
# 比较与展示
# --------------------------------------------------------------------------------------
def count_findings(text: str) -> int:
    """粗略统计评审条数：以 [级别] / 数字序号 / 列表符号开头的行。"""
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("[", "-", "*", "•")) or (s[0].isdigit() and s[1:3].rstrip() in (".", "、", ")", ".)")):
            n += 1
    return n


def print_reviews(results: List[ReviewResult], show_reasoning: bool) -> None:
    for r in results:
        print("=" * 88)
        served = f" (served: {r.served_model})" if r.served_model and r.served_model != r.requested_model else ""
        print(f"模型: {r.requested_model}{served}")
        print("-" * 88)
        if r.error:
            print(f"[失败] {r.error}")
            if r.content:
                print(r.content)
            continue
        if show_reasoning and r.reasoning_content:
            print("[思维链]")
            print(r.reasoning_content.strip())
            print("[回答]")
        print(r.content)
    print("=" * 88)


def print_comparison(results: List[ReviewResult]) -> None:
    headers = ["指标"] + [r.requested_model for r in results]

    def fmt(v: Any) -> str:
        return "-" if v is None else str(v)

    rows = [
        ["状态", *[("OK" if r.ok else "FAILED") for r in results]],
        ["finish_reason", *[fmt(r.finish_reason) for r in results]],
        ["回答 token (completion-reasoning)", *[fmt(r.answer_tokens) for r in results]],
        ["思维链 token", *[fmt(r.reasoning_tokens) for r in results]],
        ["completion_tokens 合计", *[fmt(r.completion_tokens) for r in results]],
        ["prompt_tokens", *[fmt(r.prompt_tokens) for r in results]],
        ["评审条数(粗估)", *[fmt(count_findings(r.content)) if r.ok else "-" for r in results]],
        ["回答字符数", *[fmt(len(r.content)) if r.ok else "-" for r in results]],
        ["耗时 (s)", *[fmt(r.latency_s) for r in results]],
        ["尝试次数", *[fmt(r.attempts) for r in results]],
        ["request_id", *[fmt(r.request_id) for r in results]],
    ]
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]

    def line(cells: List[str]) -> str:
        return " | ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    print("\n对比：")
    print(line(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(line(row))
    print(
        f"\n说明：目标回答长度 ≈ {TARGET_ANSWER_TOKENS} token。kimi-k3 保留思维链（计入 completion_tokens），"
        "glm-5.3 以 reasoning_effort=low 运行，思维链应为 0。"
    )


# --------------------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="kimi-k3 vs glm-5.3 code review 对比（火山方舟 Agent Plan）")
    p.add_argument("--code-file", type=Path, help="要评审的源码文件；缺省使用内置示例")
    p.add_argument("--lang", default=None, help="代码块语言标记，缺省按文件后缀推断（示例代码为 python）")
    p.add_argument("--show-reasoning", action="store_true", help="打印 kimi-k3 的思维链（默认只打印回答）")
    p.add_argument("--json", type=Path, help="把结构化结果写到该 JSON 文件")
    p.add_argument("--timeout", type=float, default=300.0, help="单次请求超时秒数（默认 300）")
    p.add_argument("--dry-run", action="store_true", help="不调用 API，只打印将要发送的请求参数")
    return p.parse_args(argv)


def load_code(args: argparse.Namespace) -> tuple[str, str]:
    if args.code_file:
        code = args.code_file.read_text(encoding="utf-8")
        lang = args.lang or args.code_file.suffix.lstrip(".") or ""
    else:
        code, lang = DEFAULT_CODE, args.lang or "python"
    if not code.strip():
        sys.exit("代码为空，无需评审")
    return code, lang


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    code, lang = load_code(args)
    messages = build_messages(code, lang)

    if args.dry_run:
        print(f"# base_url = {AGENT_PLAN_BASE_URL}\n# api_key  = ${API_KEY_ENV}（不打印）\n")
        for cfg in MODEL_CONFIGS:
            req = build_request(cfg, messages, cfg.max_completion_tokens)
            req["messages"] = [{**m, "content": m["content"][:80] + ("…" if len(m["content"]) > 80 else "")} for m in req["messages"]]
            print(f"## {cfg.name}  —— {cfg.note}")
            print(json.dumps(req, ensure_ascii=False, indent=2), "\n")
        return 0

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(
            f"未设置环境变量 {API_KEY_ENV}。\n"
            "需要的是 Agent Plan 控制台第 3 步生成的『专属 API Key』，不是方舟 API Key "
            "（后者打 /api/plan/v3 会 401）。"
        )

    # 单例 client 复用；max_retries 处理 429/5xx 瞬时错误（SDK 自带指数退避）。
    client = OpenAI(base_url=AGENT_PLAN_BASE_URL, api_key=api_key, timeout=args.timeout, max_retries=2)

    print(f"正在用 {', '.join(c.name for c in MODEL_CONFIGS)} 评审 {len(code.splitlines())} 行 {lang or 'code'} …", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=len(MODEL_CONFIGS)) as pool:
        results = list(pool.map(lambda cfg: review_with_model(client, cfg, messages), MODEL_CONFIGS))

    print_reviews(results, show_reasoning=args.show_reasoning)
    print_comparison(results)

    if args.json:
        payload = {
            "base_url": AGENT_PLAN_BASE_URL,
            "target_answer_tokens": TARGET_ANSWER_TOKENS,
            "code_lang": lang,
            "results": [asdict(r) | {"answer_tokens": r.answer_tokens, "ok": r.ok} for r in results],
        }
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化结果已写入 {args.json}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
