#!/usr/bin/env python3
"""批量用智谱 GLM(OpenAI 兼容接口)给 Python 文件补 docstring。

用法示例::

    export ZHIPU_API_KEY="你的 key"
    python glm_docstring.py ./src                # 只预览 diff, 不写文件
    python glm_docstring.py ./src --write        # 原地写入
    python glm_docstring.py a.py b.py --write --backup --lang zh --style google

安全策略:
  * 脚本只向模型索取 "限定名 -> docstring 文本" 的 JSON, 不让模型改写整份源码,
    然后用 ast 定位插入位置, 保证除了新增 docstring 之外代码一字不动。
  * 只给 **缺少** docstring 的模块 / 类 / 函数 / 方法补, 已有的不动 (除非 --overwrite)。
  * 写回前用 ast.parse 校验, 解析失败的文件一律跳过。
"""

from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    sys.exit("缺少 openai SDK, 请先执行: pip install 'openai>=1.0'")

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

# Coding Plan 套餐使用的是独立的 coding 端点, 不是普通按量付费端点
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
# 普通按量付费 / 体验中心 key 用这个
FALLBACK_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

DEFAULT_MODEL = "glm-5.3"
API_KEY_ENV_NAMES = ("ZHIPU_API_KEY", "ZHIPUAI_API_KEY", "GLM_API_KEY", "ZAI_API_KEY")

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", "build", "dist", "site-packages", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", ".eggs",
}

STYLE_HINTS = {
    "google": "Google 风格 (Args: / Returns: / Raises: 小节)",
    "numpy": "NumPy 风格 (Parameters / Returns / Raises 小节, 下划线分隔)",
    "sphinx": "Sphinx/reST 风格 (:param x: / :returns: / :raises:)",
    "plain": "简洁的一到三句话描述, 不加参数小节",
}

LANG_HINTS = {
    "zh": "使用简体中文书写 docstring (标识符、类型名保持英文)",
    "en": "Write the docstrings in English",
}

SYSTEM_PROMPT = """你是一名资深 Python 工程师, 专门负责为代码补充高质量的 docstring。
规则:
1. 只输出一个 JSON 对象, 形如 {"docstrings": {"<qualname>": "<docstring 文本>", ...}}, 不要输出任何其他文字或 Markdown 代码块。
2. 只为我在 targets 列表中给出的限定名 (qualname) 生成 docstring, 不要多写、不要少写、不要改名。
3. docstring 文本不要包含三引号, 不要包含前导/尾随空行; 多行时首行是一句话摘要, 空一行后再写细节。
4. 描述要基于代码的真实行为, 不确定的不要编造; 私有细节和显而易见的 getter 可以只写一句话。
5. 参数、返回值、异常尽量写全; 类型以代码中的注解为准。
"""


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass
class Target:
    qualname: str          # 例如 "module", "MyClass", "MyClass.method", "func"
    kind: str              # module / class / function / method
    insert_line: int       # 1-based, 在这一行之前插入
    indent: str            # 插入行的缩进
    signature: str         # 给模型看的简短签名
    replace_range: tuple[int, int] | None = None  # 覆盖模式下要删掉的旧 docstring 行区间 (1-based, 含)


@dataclass
class FileResult:
    path: Path
    status: str            # ok / skipped / error / unchanged
    message: str = ""
    added: int = 0
    diff: str = ""
    new_source: str | None = None
    targets: list[Target] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 源码分析
# --------------------------------------------------------------------------- #

def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _docstring_range(node: ast.AST) -> tuple[int, int] | None:
    """返回现有 docstring 语句占用的行区间 (1-based, 含), 没有则 None。"""
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.lineno, first.end_lineno or first.lineno
    return None


def collect_targets(
    source: str,
    lines: list[str],
    *,
    include_private: bool,
    overwrite: bool,
    include_module: bool,
) -> tuple[ast.Module, list[Target]]:
    tree = ast.parse(source)
    targets: list[Target] = []

    # ---- 模块级 docstring ----
    if include_module:
        existing = _docstring_range(tree)
        if existing is None or overwrite:
            insert_line = 1
            # 跳过 shebang / 编码声明 / 紧随其后的注释头
            for i, line in enumerate(lines, start=1):
                s = line.strip()
                if i <= 2 and (s.startswith("#!") or re.match(r"#.*coding[:=]", s)):
                    insert_line = i + 1
                    continue
                break
            targets.append(
                Target(
                    qualname="module",
                    kind="module",
                    insert_line=existing[0] if existing else insert_line,
                    indent="",
                    signature="(module)",
                    replace_range=existing if overwrite else None,
                )
            )

    # ---- 类 / 函数 / 方法 ----
    def visit(node: ast.AST, prefix: str, in_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = child.name
                qual = f"{prefix}.{name}" if prefix else name
                is_cls = isinstance(child, ast.ClassDef)
                kind = "class" if is_cls else ("method" if in_class else "function")

                if include_private or not _is_private(name):
                    existing = _docstring_range(child)
                    if existing is None or overwrite:
                        first = child.body[0]
                        body_line = lines[first.lineno - 1]
                        # 单行定义 (def f(): return 1) 无法安全插入, 跳过
                        if body_line[: first.col_offset].strip() == "":
                            indent = body_line[: first.col_offset]
                            sig_end = first.lineno - 1
                            sig = "\n".join(
                                l.rstrip() for l in lines[child.lineno - 1: sig_end]
                            ).strip()
                            targets.append(
                                Target(
                                    qualname=qual,
                                    kind=kind,
                                    insert_line=first.lineno,
                                    indent=indent,
                                    signature=sig[:400],
                                    replace_range=existing if (overwrite and existing) else None,
                                )
                            )
                # 递归: 类里的方法 / 嵌套类; 函数内部的嵌套函数一般不需要 docstring, 不递归
                if is_cls:
                    visit(child, qual, True)
            elif isinstance(child, (ast.If, ast.Try, ast.With)):
                # 允许 if TYPE_CHECKING: / try: 里定义的顶层类和函数
                visit(child, prefix, in_class)

    visit(tree, "", False)
    return tree, targets


# --------------------------------------------------------------------------- #
# 模型调用
# --------------------------------------------------------------------------- #

def _strip_code_fence(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return m.group(1) if m else text


def _extract_json(text: str) -> dict:
    text = _strip_code_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 模型偶尔会在 JSON 前后夹杂文字, 取最外层大括号再试一次
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start: end + 1])
        raise


def request_docstrings(
    client: OpenAI,
    *,
    model: str,
    source: str,
    rel_path: str,
    targets: list[Target],
    lang: str,
    style: str,
    thinking: bool,
    temperature: float,
) -> dict[str, str]:
    target_desc = "\n".join(f"- {t.qualname}  [{t.kind}]  {t.signature.splitlines()[0] if t.signature else ''}" for t in targets)
    user_prompt = (
        f"文件: {rel_path}\n"
        f"要求: {LANG_HINTS[lang]}; {STYLE_HINTS[style]}。\n\n"
        f"targets (只为这些限定名生成 docstring):\n{target_desc}\n\n"
        f"源码:\n```python\n{source}\n```\n\n"
        '只返回 JSON: {"docstrings": {"<qualname>": "<docstring>"}}'
    )

    extra_body: dict = {}
    if not thinking:
        # GLM 系列默认开启思考模式; 补 docstring 这种任务关掉更快更省
        extra_body["thinking"] = {"type": "disabled"}

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        extra_body=extra_body or None,
    )
    content = resp.choices[0].message.content or ""
    data = _extract_json(content)
    docs = data.get("docstrings", data)
    if not isinstance(docs, dict):
        raise ValueError(f"模型返回格式不符: {content[:200]!r}")
    return {str(k): str(v) for k, v in docs.items() if isinstance(v, str) and v.strip()}


# --------------------------------------------------------------------------- #
# 插入 docstring
# --------------------------------------------------------------------------- #

def format_docstring(text: str, indent: str) -> list[str]:
    text = text.strip().replace('"""', "'''")
    # 含反斜杠 (如 Windows 路径、正则) 时用 raw docstring, 避免无效转义警告
    prefix = 'r"""' if "\\" in text else '"""'
    doc_lines = [l.rstrip() for l in text.splitlines()]
    while doc_lines and not doc_lines[-1]:
        doc_lines.pop()
    if len(doc_lines) == 1:
        return [f'{indent}{prefix}{doc_lines[0]}"""\n']
    out = [f'{indent}{prefix}{doc_lines[0]}\n']
    for l in doc_lines[1:]:
        out.append(f"{indent}{l}\n" if l else "\n")
    out.append(f'{indent}"""\n')
    return out


def apply_docstrings(lines: list[str], targets: list[Target], docs: dict[str, str]) -> tuple[list[str], int]:
    new_lines = list(lines)
    added = 0
    # 从后往前插, 行号不会漂移
    for t in sorted(targets, key=lambda x: x.insert_line, reverse=True):
        text = docs.get(t.qualname)
        if not text:
            continue
        block = format_docstring(text, t.indent)
        if t.replace_range:
            s, e = t.replace_range
            new_lines[s - 1: e] = block
        else:
            idx = t.insert_line - 1
            new_lines[idx:idx] = block
            # 模块 / 类 docstring 后面如果紧接着代码, 补一个空行更好看
            nxt = idx + len(block)
            if t.kind in ("module", "class") and nxt < len(new_lines) and new_lines[nxt].strip():
                new_lines.insert(nxt, "\n")
        added += 1
    return new_lines, added


# --------------------------------------------------------------------------- #
# 单文件处理
# --------------------------------------------------------------------------- #

def process_file(path: Path, root: Path, client: OpenAI, args: argparse.Namespace) -> FileResult:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return FileResult(path, "skipped", "非 UTF-8 编码")

    if len(source) > args.max_chars:
        return FileResult(path, "skipped", f"文件过大 ({len(source)} 字符 > --max-chars {args.max_chars})")

    lines = source.splitlines(keepends=True)
    try:
        _, targets = collect_targets(
            source, lines,
            include_private=args.include_private,
            overwrite=args.overwrite,
            include_module=not args.no_module,
        )
    except SyntaxError as e:
        return FileResult(path, "error", f"语法错误, 跳过: {e}")

    if not targets:
        return FileResult(path, "unchanged", "所有对象已有 docstring")

    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    try:
        docs = request_docstrings(
            client,
            model=args.model,
            source=source,
            rel_path=rel,
            targets=targets,
            lang=args.lang,
            style=args.style,
            thinking=args.thinking,
            temperature=args.temperature,
        )
    except Exception as e:  # noqa: BLE001 - 想把所有 API/解析错误都报出来而不是中断批处理
        return FileResult(path, "error", f"模型调用失败: {type(e).__name__}: {e}", targets=targets)

    new_lines, added = apply_docstrings(lines, targets, docs)
    new_source = "".join(new_lines)

    try:
        ast.parse(new_source)
    except SyntaxError as e:
        return FileResult(path, "error", f"插入后语法校验失败, 未写入: {e}", targets=targets)

    if new_source == source:
        return FileResult(path, "unchanged", "模型没有返回任何可用的 docstring", targets=targets)

    diff = "".join(difflib.unified_diff(lines, new_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}"))
    missing = [t.qualname for t in targets if t.qualname not in docs]
    msg = f"新增 {added}/{len(targets)} 个 docstring"
    if missing:
        msg += f" (模型未返回: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''})"
    return FileResult(path, "ok", msg, added=added, diff=diff, new_source=new_source, targets=targets)


# --------------------------------------------------------------------------- #
# 文件发现 / CLI
# --------------------------------------------------------------------------- #

def iter_python_files(paths: Iterable[str], excludes: list[str]) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            if path.suffix == ".py":
                found.append(path.resolve())
            continue
        if not path.is_dir():
            print(f"[warn] 路径不存在: {p}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    fp = (Path(dirpath) / fn).resolve()
                    if not any(fnmatch.fnmatch(str(fp), pat) or fnmatch.fnmatch(fn, pat) for pat in excludes):
                        found.append(fp)
    # 去重保序
    seen, uniq = set(), []
    for f in found:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def get_api_key() -> str:
    for name in API_KEY_ENV_NAMES:
        val = os.environ.get(name)
        if val:
            return val.strip()
    sys.exit(
        "未找到 API Key。请设置环境变量 " + " / ".join(API_KEY_ENV_NAMES) +
        " 之一, 例如:\n  export ZHIPU_API_KEY='xxxxxxxx.xxxxxxxx'"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="用智谱 GLM 批量为 Python 文件补充 docstring (只增不改, 默认仅预览)。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("paths", nargs="+", help="要处理的 .py 文件或目录 (目录会递归)")
    p.add_argument("--write", action="store_true", help="真正写回文件; 不加则只打印 diff")
    p.add_argument("--backup", action="store_true", help="写回前先保存 <文件>.bak")
    p.add_argument("--model", default=os.environ.get("GLM_MODEL", DEFAULT_MODEL), help="模型名 (也可用环境变量 GLM_MODEL)")
    p.add_argument("--base-url", default=os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL),
                   help=f"接口地址 (也可用环境变量 GLM_BASE_URL)。Coding Plan 用默认值; 普通按量 key 用 {FALLBACK_BASE_URL}")
    p.add_argument("--lang", choices=LANG_HINTS, default="zh", help="docstring 语言")
    p.add_argument("--style", choices=STYLE_HINTS, default="google", help="docstring 风格")
    p.add_argument("--include-private", action="store_true", help="也给 _private 开头的对象写 docstring")
    p.add_argument("--no-module", action="store_true", help="不生成模块级 docstring")
    p.add_argument("--overwrite", action="store_true", help="已有 docstring 的也重写 (慎用)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="排除的文件 glob, 可重复 (如 'test_*.py')")
    p.add_argument("--workers", type=int, default=4, help="并发请求数; 遇到 429 限流请调小")
    p.add_argument("--max-chars", type=int, default=120_000, help="单文件最大字符数, 超过则跳过")
    p.add_argument("--thinking", action="store_true", help="开启模型思考模式 (更慢, 一般不需要)")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--timeout", type=float, default=180.0, help="单次请求超时秒数")
    p.add_argument("--max-retries", type=int, default=3, help="SDK 自动重试次数 (429/5xx/网络错误)")
    p.add_argument("--quiet", action="store_true", help="不打印 diff, 只打印每个文件的结果")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = get_api_key()

    client = OpenAI(
        api_key=api_key,
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )

    files = iter_python_files(args.paths, args.exclude)
    if not files:
        print("没有找到 .py 文件。")
        return 1

    root = Path(os.path.commonpath([str(f.parent) for f in files])) if len(files) > 1 else files[0].parent
    mode = "写入模式" if args.write else "预览模式 (加 --write 才会修改文件)"
    print(f"模型: {args.model} | 接口: {args.base_url} | 文件数: {len(files)} | {mode}\n")

    print_lock = threading.Lock()
    stats = {"ok": 0, "unchanged": 0, "skipped": 0, "error": 0, "added": 0}

    def handle(result: FileResult) -> None:
        stats[result.status] += 1
        stats["added"] += result.added
        with print_lock:
            tag = {"ok": "OK  ", "unchanged": "SAME", "skipped": "SKIP", "error": "ERR "}[result.status]
            print(f"[{tag}] {result.path}: {result.message}")
            if result.status == "ok":
                if not args.quiet and not args.write:
                    print(result.diff)
                if args.write and result.new_source is not None:
                    if args.backup:
                        result.path.with_suffix(result.path.suffix + ".bak").write_text(
                            result.path.read_text(encoding="utf-8"), encoding="utf-8"
                        )
                    result.path.write_text(result.new_source, encoding="utf-8")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(process_file, f, root, client, args): f for f in files}
        for fut in as_completed(futures):
            try:
                handle(fut.result())
            except Exception as e:  # noqa: BLE001
                stats["error"] += 1
                print(f"[ERR ] {futures[fut]}: 未预期的异常 {type(e).__name__}: {e}")

    print(
        f"\n完成: 修改 {stats['ok']} 个文件, 新增 {stats['added']} 个 docstring; "
        f"无需修改 {stats['unchanged']}, 跳过 {stats['skipped']}, 失败 {stats['error']}。"
    )
    if not args.write and stats["ok"]:
        print("以上为预览。确认无误后加 --write (建议同时加 --backup) 真正写入。")
    return 0 if stats["error"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
