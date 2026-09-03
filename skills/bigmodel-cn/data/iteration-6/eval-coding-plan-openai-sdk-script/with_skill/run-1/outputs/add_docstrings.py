#!/usr/bin/env python3
"""批量为 Python 文件补写 docstring —— 智谱 GLM Coding Plan（openai SDK 兼容层）。

工作方式（安全优先）：
  1. 用 ast 扫描每个 .py 文件，找出缺少 docstring 的模块 / 类 / 函数 / 方法；
  2. 把带行号的源码 + 待补目标列表发给 glm-5.3，要求只返回一个 JSON（键 -> docstring 文本）；
  3. 脚本自己把 docstring 按正确缩进插到源码里，并用 ast.parse 校验结果；
     模型**从不**直接改写你的代码，只提供 docstring 文本。

默认是「预览模式」：只在终端打印 diff，不落盘。加 --in-place 才会写回原文件
（默认会先备份成 .bak），或用 --out-dir 写到另一个目录。

依赖：pip install --upgrade "openai>=1.0"
环境变量：GLM_CODING_PLAN_API_KEY（Coding Plan 套餐 Key，不是开放平台按量 Key）
"""

from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeVar

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
except ImportError:  # pragma: no cover
    sys.exit("缺少 openai SDK，请先执行：pip install --upgrade 'openai>=1.0'")

# ---------------------------------------------------------------------------
# 常量：两套隔离的计费体系，Key 与 Base URL 必须配套
# ---------------------------------------------------------------------------
CODING_PLAN_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"  # 套餐 Key 专用，注意多了 /coding
STANDARD_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"  # 开放平台按量 Key
CODING_PLAN_ENV = "GLM_CODING_PLAN_API_KEY"
STANDARD_ENV = "ZHIPUAI_API_KEY"

DEFAULT_MODEL = "glm-5.3"
CODING_PLAN_MODELS = {"glm-5.3", "glm-5.3-flash"}  # 套餐内可用模型；旧代码会被自动路由

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    ".tox", ".nox", ".eggs",
}

# 429 里值得退避重试的业务错误码（账户限流 / 平台过载 / 用量上限）
RETRYABLE_BIZ_CODES = {"1302", "1305", "1308", "1310"}

HINT_1113 = (
    "收到业务错误码 1113（余额不足或无可用资源包）。\n"
    "  如果你用的是 GLM Coding Plan 套餐 Key，这几乎总是 Base URL 用错了：\n"
    f"  套餐 Key 必须打 {CODING_PLAN_BASE_URL}（当前脚本默认值），\n"
    f"  打到 {STANDARD_BASE_URL} 会看不到套餐额度，直接报 1113 —— 不需要充值。\n"
    "  如果你确认是开放平台按量 Key，请用 --standard-api 运行，并到控制台查看余额。"
)

T = TypeVar("T")

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, file=sys.stderr, flush=True)


class FatalError(RuntimeError):
    """配置类错误（Key/Base URL/模型/权限），重试无意义，应立即终止整个批处理。"""


class FileError(RuntimeError):
    """单个文件处理失败，不影响其它文件。"""


# ---------------------------------------------------------------------------
# 第一步：用 ast 找出缺 docstring 的目标
# ---------------------------------------------------------------------------
@dataclass
class Target:
    key: str            # 发给模型 / 回填时用的唯一键，如 "Foo.bar#L12"
    kind: str           # module / class / function / method
    qualname: str
    def_lineno: int     # 定义所在行（模块为 0）
    insert_before: int  # 在这一行（1-based）之前插入 docstring
    indent: str         # docstring 的缩进
    signature: str      # 给模型看的定义行（多行签名会拼在一起）


def _is_private(name: str) -> bool:
    return name.startswith("_")


def collect_targets(
    source: str, *, include_private: bool, include_module: bool
) -> tuple[list[Target], list[str]]:
    """返回 (待补 docstring 的目标, 被跳过的说明)。source 必须已经是 \\n 换行。"""
    tree = ast.parse(source)
    lines = source.split("\n")
    targets: list[Target] = []
    skipped: list[str] = []

    if include_module and ast.get_docstring(tree, clean=False) is None:
        insert = 1
        for i, line in enumerate(lines[:2]):
            if line.startswith("#!") or re.match(r"^#.*coding[:=]", line):
                insert = i + 2
        targets.append(Target("<module>#L0", "module", "<module>", 0, insert, "", ""))

    stack: list[str] = []

    def handle(node: ast.AST, kind: str) -> None:
        name = node.name  # type: ignore[attr-defined]
        qualname = ".".join(stack + [name])
        if not include_private and _is_private(name):
            return
        if ast.get_docstring(node, clean=False) is not None:  # type: ignore[arg-type]
            return
        first = node.body[0]  # type: ignore[attr-defined]
        body_line = lines[first.lineno - 1]
        # 单行定义（def f(): return 1）没法安全插 docstring，跳过
        if first.lineno == node.lineno or body_line[: first.col_offset].strip():
            skipped.append(f"{qualname}（第 {node.lineno} 行）是单行定义，已跳过")
            return
        indent = body_line[: first.col_offset]
        signature = " ".join(
            l.strip() for l in lines[node.lineno - 1 : first.lineno - 1] if l.strip()
        )
        targets.append(
            Target(f"{qualname}#L{node.lineno}", kind, qualname, node.lineno,
                   first.lineno, indent, signature)
        )

    def visit(node: ast.AST, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                handle(child, "class")
                stack.append(child.name)
                visit(child, True)
                stack.pop()
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                handle(child, "method" if in_class else "function")
                stack.append(child.name)
                visit(child, False)
                stack.pop()
            else:
                visit(child, in_class)

    visit(tree, False)
    return targets, skipped


# ---------------------------------------------------------------------------
# 第二步：构造 prompt，让模型只返回 JSON
# ---------------------------------------------------------------------------
STYLE_GUIDE = {
    "google": "Google 风格（Args: / Returns: / Raises: / Yields: 分节，缩进 4 空格）",
    "numpy": "NumPy 风格（Parameters / Returns / Raises 分节，下划线分隔）",
    "sphinx": "Sphinx/reST 风格（:param x: / :type x: / :returns: / :raises:）",
}
LANG_GUIDE = {"zh": "简体中文", "en": "English"}


def build_messages(
    rel_path: str, source: str, targets: list[Target], *, style: str, lang: str,
    fix_hint: str | None = None,
) -> list[dict]:
    numbered = "\n".join(f"{i + 1:5d}| {line}" for i, line in enumerate(source.split("\n")))
    target_lines = "\n".join(
        f'- key: "{t.key}"  ({t.kind})  {t.signature or "模块级 docstring"}' for t in targets
    )
    system = (
        "你是资深 Python 工程师，专门为现有代码补写高质量 docstring。"
        "你只输出一个 JSON 对象，不输出任何解释、Markdown 或代码块围栏。"
    )
    user = f"""下面是文件 `{rel_path}` 的完整源码（每行前面是行号，行号不是代码的一部分）：

{numbered}

请为下列目标补写 docstring（这些目标目前没有 docstring）：
{target_lines}

要求：
1. 使用 {STYLE_GUIDE[style]}，语言为 {LANG_GUIDE[lang]}；专有名词、参数名、类型名保持原文。
2. 第一行是一句简洁的摘要（以句号结尾）；如需展开，空一行后再写细节。
3. 函数/方法：根据签名和实现如实描述参数、返回值、可能抛出的异常、副作用；有 yield 就写 Yields。
   不要臆造代码中不存在的行为；无法确定的地方宁可少写，也不要编造。
4. 类：描述职责与主要属性；模块：描述模块用途与主要内容。
5. docstring 文本里**不要**包含三引号，不要带缩进前缀（脚本会自动缩进），不要带首尾空行。
6. 只返回如下结构的 JSON，键必须与上面给出的 key 完全一致，一个都不能少：
{{"docstrings": {{"<key>": "<docstring 文本，多行用 \\n>", ...}}}}
"""
    if fix_hint:
        user += f"\n注意：{fix_hint}\n"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$", re.MULTILINE)


def parse_docstring_json(content: str, expected_keys: Iterable[str]) -> dict[str, str]:
    """把模型输出解析成 {key: docstring}。json_object 模式也不能 100% 保证合法，要兜底。"""
    text = _FENCE_RE.sub("", content.strip()).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("响应里找不到 JSON 对象")
        text = text[start : end + 1]
    data = json.loads(text)
    docs = data.get("docstrings", data) if isinstance(data, dict) else None
    if not isinstance(docs, dict):
        raise ValueError("JSON 顶层缺少 docstrings 对象")
    result: dict[str, str] = {}
    for key in expected_keys:
        value = docs.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# 第三步：把 docstring 插回源码
# ---------------------------------------------------------------------------
def format_docstring(text: str, indent: str) -> list[str]:
    text = text.replace("\r\n", "\n").strip("\n").strip()
    text = text.replace('"""', "'''")
    text = text.rstrip("\\")
    prefix = "r" if "\\" in text else ""
    if text.endswith('"'):
        text += " "
    parts = text.split("\n")
    if len(parts) == 1:
        return [f'{indent}{prefix}"""{parts[0]}"""']
    out = [f'{indent}{prefix}"""{parts[0]}']
    for line in parts[1:]:
        out.append(f"{indent}{line.rstrip()}" if line.strip() else "")
    out.append(f'{indent}"""')
    return out


def apply_docstrings(source: str, targets: list[Target], docs: dict[str, str]) -> str:
    lines = source.split("\n")
    for t in sorted(targets, key=lambda x: x.insert_before, reverse=True):
        if t.key not in docs:
            continue
        block = format_docstring(docs[t.key], t.indent)
        if t.kind == "module":
            # 模块 docstring 后面留一个空行，除非下一行本来就是空行
            if t.insert_before - 1 < len(lines) and lines[t.insert_before - 1].strip():
                block.append("")
        lines[t.insert_before - 1 : t.insert_before - 1] = block
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API 调用：区分「配置错误立即终止」与「限流/过载指数退避」
# ---------------------------------------------------------------------------
def _biz_code(err: APIStatusError) -> str | None:
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict) and inner.get("code") is not None:
            return str(inner["code"])
    m = re.search(r'"code"\s*:\s*"?(\d{4})"?', str(err))
    return m.group(1) if m else None


def call_with_retry(fn: Callable[[], T], *, attempts: int, base_delay: float, label: str) -> T:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except APIStatusError as err:
            code = _biz_code(err)
            status = err.status_code
            if code == "1113":
                raise FatalError(HINT_1113) from err
            if status in (401, 403):
                raise FatalError(
                    f"鉴权/权限失败（HTTP {status}，业务码 {code}）：检查环境变量里的 Key 是否正确、"
                    "是否把套餐 Key 与开放平台 Key 弄混。"
                ) from err
            if code == "1211":
                raise FatalError(f"模型不存在（1211）：{err}。Coding Plan 只支持 {sorted(CODING_PLAN_MODELS)}。") from err
            if status == 404:
                raise FatalError(
                    f"HTTP 404：{err}\n  检查 --base-url 是否正好以 /coding/paas/v4 结尾（不要多拼 /v1）。"
                ) from err
            retryable = status >= 500 or (status == 429 and (code is None or code in RETRYABLE_BIZ_CODES))
            if not retryable:
                raise FileError(f"请求被拒绝（HTTP {status}，业务码 {code}）：{err}") from err
            if attempt == attempts:
                raise FileError(f"重试 {attempts} 次后仍失败（HTTP {status}，业务码 {code}）：{err}") from err
            reason = f"HTTP {status} 业务码 {code}"
        except (APIConnectionError, APITimeoutError) as err:
            if attempt == attempts:
                raise FileError(f"网络错误，重试 {attempts} 次后放弃：{err}") from err
            reason = f"网络错误 {type(err).__name__}"
        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
        log(f"  [{label}] {reason}，{delay:.1f}s 后第 {attempt + 1}/{attempts} 次重试")
        time.sleep(delay)
    raise AssertionError("unreachable")


@dataclass
class Usage:
    prompt: int = 0
    completion: int = 0
    reasoning: int = 0
    requests: int = 0

    def add(self, usage) -> None:
        if usage is None:
            return
        self.requests += 1
        self.prompt += getattr(usage, "prompt_tokens", 0) or 0
        self.completion += getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "completion_tokens_details", None)
        self.reasoning += (getattr(details, "reasoning_tokens", 0) or 0) if details else 0


def request_docstrings(
    client: OpenAI, args: argparse.Namespace, rel_path: str, source: str,
    targets: list[Target], usage: Usage,
) -> dict[str, str]:
    expected = [t.key for t in targets]
    fix_hint: str | None = None
    last_err: Exception | None = None
    merged: dict[str, str] = {}
    for round_no in range(1, args.json_retries + 2):
        messages = build_messages(rel_path, source, targets, style=args.style, lang=args.lang, fix_hint=fix_hint)

        def do_request():
            return client.chat.completions.create(
                model=args.model,
                messages=messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                # json_schema 目前会被静默忽略，只能用 json_object + prompt 描述结构 + 客户端校验
                response_format={"type": "json_object"},
                # glm-5.3 强制开启思考，无法关闭；写 docstring 用 low 档最省额度（思考 token 也按输出计费）
                extra_body={"reasoning_effort": args.reasoning_effort},
            )

        resp = call_with_retry(do_request, attempts=args.retries, base_delay=args.retry_delay, label=rel_path)
        usage.add(getattr(resp, "usage", None))
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise FileError(f"输出被 max_tokens={args.max_tokens} 截断，请调大 --max-tokens 或拆分文件")
        if choice.finish_reason not in (None, "stop"):
            raise FileError(f"模型异常结束：finish_reason={choice.finish_reason}")
        content = choice.message.content or ""
        try:
            docs = parse_docstring_json(content, expected)
        except (ValueError, json.JSONDecodeError) as err:
            last_err = err
            fix_hint = "上一次的输出不是合法 JSON，这次务必只输出一个合法 JSON 对象，不要任何多余文字。"
            log(f"  [{rel_path}] 第 {round_no} 轮输出解析失败：{err}")
            continue
        merged.update(docs)
        missing = [k for k in expected if k not in merged]
        if not missing:
            return merged
        if round_no <= args.json_retries:
            fix_hint = "上一次漏掉了这些 key，请补全所有 key：" + ", ".join(missing)
            log(f"  [{rel_path}] 第 {round_no} 轮缺少 {len(missing)} 个目标，重试补全")
    if not merged and last_err is not None:
        raise FileError(f"模型连续 {args.json_retries + 1} 次未返回可解析的 JSON：{last_err}")
    return merged


# ---------------------------------------------------------------------------
# 文件级流程
# ---------------------------------------------------------------------------
@dataclass
class FileResult:
    path: Path
    status: str  # ok / unchanged / skipped / error
    detail: str = ""
    added: int = 0


def write_text(path: Path, text: str) -> None:
    """按原样写出（newline="" 防止 Python 在 Windows 上把 \n 再转成 \r\n）。"""
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def iter_python_files(inputs: list[str], excludes: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_file():
            if p.suffix == ".py":
                files.append(p)
            continue
        if not p.is_dir():
            log(f"警告：路径不存在，已忽略：{raw}")
            continue
        for root, dirs, names in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(names):
                if name.endswith(".py"):
                    files.append(Path(root) / name)
    result = []
    for f in dict.fromkeys(files):
        s = str(f)
        if any(fnmatch.fnmatch(s, pat) or fnmatch.fnmatch(f.name, pat) for pat in excludes):
            continue
        result.append(f)
    return result


def process_file(client: OpenAI, args: argparse.Namespace, path: Path, usage: Usage) -> FileResult:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return FileResult(path, "skipped", "不是 UTF-8 文本")
    newline = "\r\n" if "\r\n" in raw else "\n"
    source = raw.replace("\r\n", "\n")
    if len(source) > args.max_file_chars:
        return FileResult(path, "skipped", f"文件超过 {args.max_file_chars} 字符，请调大 --max-file-chars 或拆分")
    try:
        targets, skipped = collect_targets(
            source, include_private=args.include_private, include_module=not args.skip_module
        )
    except SyntaxError as err:
        return FileResult(path, "skipped", f"语法错误，无法解析：{err}")
    for note in skipped:
        log(f"  [{path}] {note}")
    if not targets:
        return FileResult(path, "unchanged", "所有目标已有 docstring")

    docs = request_docstrings(client, args, str(path), source, targets, usage)
    if not docs:
        return FileResult(path, "error", "模型没有返回任何可用 docstring")
    new_source = apply_docstrings(source, targets, docs)
    try:
        ast.parse(new_source)
    except SyntaxError as err:
        return FileResult(path, "error", f"插入 docstring 后语法校验失败，未写入：{err}")

    added = len(docs)
    missing = len(targets) - added
    detail = f"补写 {added} 处" + (f"，{missing} 处模型未返回" if missing else "")
    out_text = new_source.replace("\n", newline) if newline != "\n" else new_source

    if args.in_place:
        if not args.no_backup:
            write_text(path.with_suffix(path.suffix + ".bak"), raw)
        write_text(path, out_text)
    elif args.out_dir:
        base = next((Path(i) for i in args.inputs if Path(i).is_dir() and path.is_relative_to(Path(i))), path.parent)
        dest = Path(args.out_dir) / path.relative_to(base)
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_text(dest, out_text)
        detail += f" -> {dest}"
    else:
        diff = difflib.unified_diff(
            source.split("\n"), new_source.split("\n"),
            fromfile=str(path), tofile=f"{path} (with docstrings)", lineterm="",
        )
        with _print_lock:
            print("\n".join(diff))
            print()
    return FileResult(path, "ok", detail, added)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="用智谱 GLM Coding Plan（glm-5.3）批量为 Python 文件补写 docstring。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  export GLM_CODING_PLAN_API_KEY=你的套餐Key\n"
            "  python add_docstrings.py src/                 # 预览 diff，不写文件\n"
            "  python add_docstrings.py src/ --in-place      # 原地写回（自动备份 .bak）\n"
            "  python add_docstrings.py a.py b.py --out-dir out/ --lang en --style numpy\n"
        ),
    )
    p.add_argument("inputs", nargs="+", help=".py 文件或目录（目录会递归扫描）")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--in-place", action="store_true", help="直接写回原文件（默认先备份为 .bak）")
    mode.add_argument("--out-dir", help="把结果写到这个目录（保持相对路径），不动原文件")
    p.add_argument("--no-backup", action="store_true", help="配合 --in-place：不生成 .bak 备份")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="排除的文件模式，可重复，如 --exclude 'test_*.py'")
    p.add_argument("--include-private", action="store_true", help="也处理下划线开头的私有成员")
    p.add_argument("--skip-module", action="store_true", help="不补写模块级 docstring")
    p.add_argument("--style", choices=sorted(STYLE_GUIDE), default="google", help="docstring 风格（默认 google）")
    p.add_argument("--lang", choices=sorted(LANG_GUIDE), default="zh", help="docstring 语言（默认 zh）")

    api = p.add_argument_group("API 设置")
    api.add_argument("--standard-api", action="store_true",
                     help=f"改用开放平台按量 Key（{STANDARD_ENV}）和 {STANDARD_BASE_URL}")
    api.add_argument("--api-key-env", help=f"读取 Key 的环境变量名（默认 {CODING_PLAN_ENV}；--standard-api 时为 {STANDARD_ENV}）")
    api.add_argument("--base-url", help="覆盖 Base URL（一般不需要）")
    api.add_argument("--model", default=DEFAULT_MODEL, help=f"模型（默认 {DEFAULT_MODEL}；套餐内还可用 glm-5.3-flash）")
    api.add_argument("--reasoning-effort", choices=["low", "high", "max"], default="low",
                     help="glm-5.3 思考强度，无法关闭；默认 low 最省额度")
    api.add_argument("--temperature", type=float, default=0.3, help="采样温度，区间 (0,1)（默认 0.3）")
    api.add_argument("--max-tokens", type=int, default=16384, help="单次输出 token 上限（默认 16384，上限 131072）")
    api.add_argument("--timeout", type=float, default=300.0, help="单次请求超时秒数（默认 300）")
    api.add_argument("--concurrency", type=int, default=2, help="并发文件数（默认 2；限流按并发数算，别开太大）")
    api.add_argument("--retries", type=int, default=5, help="429/5xx/网络错误的最大尝试次数（默认 5，指数退避）")
    api.add_argument("--retry-delay", type=float, default=2.0, help="退避基础秒数（默认 2）")
    api.add_argument("--json-retries", type=int, default=1, help="模型返回的 JSON 不合法/不完整时的追加重试次数（默认 1）")
    api.add_argument("--max-file-chars", type=int, default=200_000, help="单文件字符上限，超过则跳过（默认 200000）")
    return p


def make_client(args: argparse.Namespace) -> OpenAI:
    env_name = args.api_key_env or (STANDARD_ENV if args.standard_api else CODING_PLAN_ENV)
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise FatalError(
            f"环境变量 {env_name} 为空。请先 export {env_name}=你的Key\n"
            "  Coding Plan 套餐 Key 在 https://bigmodel.cn/coding-plan/personal/overview 新建（团队版在「团队编程套餐 > 我的套餐」）；\n"
            "  它和开放平台 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 的按量 Key 不通用。"
        )
    base_url = args.base_url or (STANDARD_BASE_URL if args.standard_api else CODING_PLAN_BASE_URL)
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        log("警告：Base URL 以 /v1 结尾，智谱端点路径没有 /v1 这一级，多半会 404")
    if args.temperature is not None and not (0 < args.temperature < 1):
        log("警告：智谱 temperature 合法区间是 (0,1)，当前取值可能报 1214 参数非法")
    if not args.standard_api and args.model.lower() not in CODING_PLAN_MODELS:
        log(f"警告：模型 {args.model} 不在 Coding Plan 套餐列表 {sorted(CODING_PLAN_MODELS)} 内，"
            "旧版 glm 代码会被自动路由，其它模型可能直接报错")
    # max_retries=0：SDK 自带重试不认识智谱的业务错误码（会盲目重试 1113），退避逻辑由本脚本接管
    return OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout, max_retries=0)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = make_client(args)
    except FatalError as err:
        log(f"错误：{err}")
        return 2

    files = iter_python_files(args.inputs, args.exclude)
    if not files:
        log("没有找到任何 .py 文件")
        return 1
    log(f"共 {len(files)} 个文件，模型 {args.model}，Base URL {client.base_url}，并发 {args.concurrency}"
        + ("" if args.in_place or args.out_dir else "，预览模式（只打印 diff）"))

    usage = Usage()
    results: list[FileResult] = []
    fatal: FatalError | None = None
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(process_file, client, args, f, usage): f for f in files}
        try:
            for fut in as_completed(futures):
                path = futures[fut]
                try:
                    res = fut.result()
                except FatalError as err:
                    fatal = err
                    for other in futures:
                        other.cancel()
                    break
                except FileError as err:
                    res = FileResult(path, "error", str(err))
                except Exception as err:  # noqa: BLE001 —— 单文件的意外错误不应拖垮整批
                    res = FileResult(path, "error", f"{type(err).__name__}: {err}")
                results.append(res)
                mark = {"ok": "OK ", "unchanged": "--- ", "skipped": "SKIP", "error": "ERR "}[res.status]
                log(f"[{mark}] {path}  {res.detail}")
        except KeyboardInterrupt:
            log("已中断，等待进行中的请求结束…")
            for other in futures:
                other.cancel()
            return 130

    if fatal is not None:
        log(f"\n致命错误，已停止整个批处理：\n{fatal}")
        return 2

    ok = sum(1 for r in results if r.status == "ok")
    err = sum(1 for r in results if r.status == "error")
    added = sum(r.added for r in results)
    log(
        f"\n完成：{ok} 个文件补写 {added} 处 docstring，{err} 个失败，"
        f"{len(results) - ok - err} 个跳过/无需修改。\n"
        f"用量：{usage.requests} 次请求，输入 {usage.prompt} tokens，输出 {usage.completion} tokens"
        f"（其中思考 {usage.reasoning}）。套餐额度按 输入×6.9 + 输出×24 折算，输出 token 最贵。"
    )
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
