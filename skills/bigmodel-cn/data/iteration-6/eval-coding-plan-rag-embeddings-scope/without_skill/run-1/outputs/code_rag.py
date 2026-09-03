#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_rag.py —— 本地代码库 RAG 问答（智谱 embedding-3 + glm-5.3，纯 requests 调 HTTP）

用法：
    # 1) 建索引（增量：文件内容没变的不会重新向量化）
    python code_rag.py index /path/to/repo --index ./repo.index

    # 2) 单次提问
    python code_rag.py ask --index ./repo.index "这个项目的登录流程是怎么实现的？"

    # 3) 交互式问答（不带问题即进入 REPL）
    python code_rag.py ask --index ./repo.index

环境变量：
    ZHIPU_API_KEY          必填，智谱 API Key
    ZHIPU_CHAT_BASE_URL    对话接口 base url，默认 Coding Plan 专用端点
                           https://open.bigmodel.cn/api/coding/paas/v4
    ZHIPU_EMBED_BASE_URL   向量接口 base url，默认通用端点
                           https://open.bigmodel.cn/api/paas/v4
    ZHIPU_CHAT_MODEL       默认 glm-5.3
    ZHIPU_EMBED_MODEL      默认 embedding-3
    ZHIPU_EMBED_DIM        embedding 维度，默认 1024（embedding-3 支持 256/512/1024/2048）

依赖：requests, numpy
"""

import argparse
import fnmatch
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import requests

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------

API_KEY = os.environ.get("ZHIPU_API_KEY", "")
CHAT_BASE_URL = os.environ.get(
    "ZHIPU_CHAT_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"
).rstrip("/")
EMBED_BASE_URL = os.environ.get(
    "ZHIPU_EMBED_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
).rstrip("/")
CHAT_MODEL = os.environ.get("ZHIPU_CHAT_MODEL", "glm-5.3")
EMBED_MODEL = os.environ.get("ZHIPU_EMBED_MODEL", "embedding-3")
EMBED_DIM = int(os.environ.get("ZHIPU_EMBED_DIM", "1024"))

# 每次 /embeddings 请求携带多少段文本。官方对单次 batch 有上限，16 比较稳妥。
EMBED_BATCH_SIZE = 16
# 每段切片的最大字符数。embedding-3 单条输入上限约 8K token，
# 代码 token 密度高，3000 字符留足余量。
CHUNK_MAX_CHARS = 3000
CHUNK_LINES = 60          # 每段目标行数
CHUNK_OVERLAP = 10        # 相邻段重叠行数
MAX_FILE_BYTES = 1_000_000  # 超过 1MB 的文件跳过（多半是生成物/数据）

CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".java", ".kt", ".kts", ".scala", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".m", ".mm", ".dart", ".lua", ".sh", ".bash", ".zsh",
    ".sql", ".proto", ".graphql", ".gql", ".html", ".css", ".scss", ".less",
    ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json",
    ".xml", ".gradle", ".cmake", ".mk", ".dockerfile",
}
SPECIAL_FILENAMES = {"Dockerfile", "Makefile", "CMakeLists.txt", "Gemfile", "Rakefile"}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", "out", ".next", ".nuxt", ".cache", ".idea", ".vscode",
    "coverage", ".pytest_cache", ".mypy_cache", ".tox", "vendor", "third_party",
}
SKIP_GLOBS = ["*.min.js", "*.min.css", "*.lock", "package-lock.json", "yarn.lock",
              "pnpm-lock.yaml", "*.map", "*.snap"]

SYSTEM_PROMPT = (
    "你是一个资深工程师，负责根据给定的代码片段回答关于这个代码库的问题。\n"
    "规则：\n"
    "1. 只依据提供的代码片段作答；片段里没有的信息，明确说“在检索到的代码里没有看到”，不要编造。\n"
    "2. 回答时引用具体的文件路径和行号范围（例如 `src/auth.py:12-40`），方便用户跳转。\n"
    "3. 如果多个片段有关联，说明它们之间的调用关系。\n"
    "4. 用中文回答，代码保持原样。"
)

# ----------------------------------------------------------------------------
# HTTP 封装（带重试）
# ----------------------------------------------------------------------------


def _headers() -> Dict[str, str]:
    if not API_KEY:
        sys.exit("错误：请先设置环境变量 ZHIPU_API_KEY")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _post_json(url: str, payload: dict, timeout: int = 120, max_retries: int = 5) -> dict:
    """POST JSON，对 429 / 5xx / 网络错误做指数退避重试。"""
    delay = 2.0
    last_err: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=timeout)
        except requests.RequestException as e:
            last_err = f"网络错误: {e}"
        else:
            if resp.status_code == 200:
                return resp.json()
            last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
            # 4xx（除 429）通常是参数/权限问题，重试没有意义
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise RuntimeError(f"请求 {url} 失败：{last_err}")
        if attempt < max_retries:
            print(f"  [重试 {attempt}/{max_retries}] {last_err}，{delay:.0f}s 后重试…", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"请求 {url} 多次失败：{last_err}")


# ----------------------------------------------------------------------------
# Embedding
# ----------------------------------------------------------------------------


def embed_texts(texts: List[str]) -> np.ndarray:
    """调用 /embeddings，返回 shape=(len(texts), dim) 的 float32 数组。"""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    url = f"{EMBED_BASE_URL}/embeddings"
    out: List[Optional[List[float]]] = [None] * len(texts)
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        payload = {"model": EMBED_MODEL, "input": batch, "dimensions": EMBED_DIM}
        data = _post_json(url, payload)
        items = data.get("data", [])
        if len(items) != len(batch):
            raise RuntimeError(f"embedding 返回条数不符：期望 {len(batch)}，实际 {len(items)}")
        for item in items:
            idx = item.get("index", 0)
            out[start + idx] = item["embedding"]
        done = min(start + EMBED_BATCH_SIZE, len(texts))
        print(f"  向量化 {done}/{len(texts)}", file=sys.stderr, end="\r")
    print(file=sys.stderr)
    arr = np.asarray(out, dtype=np.float32)
    if arr.shape[1] != EMBED_DIM:
        # 服务端可能忽略 dimensions 参数，以实际返回为准
        print(f"  提示：返回维度为 {arr.shape[1]}，与 ZHIPU_EMBED_DIM={EMBED_DIM} 不同", file=sys.stderr)
    return arr


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


# ----------------------------------------------------------------------------
# 代码切片
# ----------------------------------------------------------------------------


def iter_source_files(root: Path, extra_exts: Iterable[str] = ()) -> Iterable[Path]:
    exts = CODE_EXTS | {e if e.startswith(".") else "." + e for e in extra_exts}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if any(fnmatch.fnmatch(fn, g) for g in SKIP_GLOBS):
                continue
            p = Path(dirpath) / fn
            if fn in SPECIAL_FILENAMES or p.suffix.lower() in exts:
                try:
                    if p.stat().st_size > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield p


def read_text(p: Path) -> Optional[str]:
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:  # 二进制
        return None
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def chunk_file(rel_path: str, text: str) -> List[dict]:
    """按行切片，带重叠；单段字符数超过 CHUNK_MAX_CHARS 时再按字符硬切。"""
    lines = text.splitlines()
    chunks: List[dict] = []
    if not lines:
        return chunks
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    i = 0
    while i < len(lines):
        j = min(i + CHUNK_LINES, len(lines))
        body = "\n".join(lines[i:j])
        if len(body) > CHUNK_MAX_CHARS:
            # 行太长（压缩过的文件等），按字符硬切
            for k in range(0, len(body), CHUNK_MAX_CHARS):
                chunks.append({"file": rel_path, "start": i + 1, "end": j, "text": body[k:k + CHUNK_MAX_CHARS]})
        else:
            chunks.append({"file": rel_path, "start": i + 1, "end": j, "text": body})
        if j >= len(lines):
            break
        i += step
    return chunks


def embed_input_for_chunk(c: dict) -> str:
    # 把文件路径放进向量化文本里，让“xxx 模块在哪”这类问题也能命中
    return f"文件: {c['file']} (第 {c['start']}-{c['end']} 行)\n{c['text']}"


def file_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()


# ----------------------------------------------------------------------------
# 索引的读写
# ----------------------------------------------------------------------------


def save_index(index_dir: Path, chunks: List[dict], vectors: np.ndarray, file_hashes: Dict[str, str], root: Path):
    index_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "root": str(root.resolve()),
        "embed_model": EMBED_MODEL,
        "dim": int(vectors.shape[1]) if vectors.size else EMBED_DIM,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "file_hashes": file_hashes,
        "chunks": chunks,
    }
    (index_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    np.save(index_dir / "vectors.npy", vectors.astype(np.float32))


def load_index(index_dir: Path) -> Tuple[dict, np.ndarray]:
    meta_path = index_dir / "meta.json"
    vec_path = index_dir / "vectors.npy"
    if not meta_path.exists() or not vec_path.exists():
        sys.exit(f"错误：索引不存在，请先运行 `index` 子命令（目录：{index_dir}）")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    vectors = np.load(vec_path)
    if len(meta["chunks"]) != vectors.shape[0]:
        sys.exit("错误：索引损坏（chunks 与 vectors 数量不一致），请重新建索引")
    return meta, vectors


# ----------------------------------------------------------------------------
# 子命令：index
# ----------------------------------------------------------------------------


def cmd_index(args: argparse.Namespace):
    root = Path(args.repo).resolve()
    if not root.is_dir():
        sys.exit(f"错误：{root} 不是目录")
    index_dir = Path(args.index)

    # 读旧索引，做增量
    old_chunks_by_file: Dict[str, List[Tuple[dict, np.ndarray]]] = {}
    old_hashes: Dict[str, str] = {}
    if index_dir.exists() and not args.rebuild:
        try:
            old_meta, old_vec = load_index(index_dir)
            if old_meta.get("embed_model") == EMBED_MODEL and old_meta.get("dim") == EMBED_DIM:
                old_hashes = old_meta.get("file_hashes", {})
                for c, v in zip(old_meta["chunks"], old_vec):
                    old_chunks_by_file.setdefault(c["file"], []).append((c, v))
                print(f"已加载旧索引：{len(old_hashes)} 个文件，{len(old_meta['chunks'])} 段", file=sys.stderr)
            else:
                print("旧索引的模型/维度与当前配置不同，将全量重建", file=sys.stderr)
        except SystemExit:
            pass

    new_chunks: List[dict] = []
    new_vectors: List[np.ndarray] = []
    pending_chunks: List[dict] = []
    file_hashes: Dict[str, str] = {}
    n_files = n_reused = 0

    for p in iter_source_files(root, args.ext or ()):
        text = read_text(p)
        if text is None or not text.strip():
            continue
        rel = p.relative_to(root).as_posix()
        h = file_hash(text)
        file_hashes[rel] = h
        n_files += 1
        if old_hashes.get(rel) == h and rel in old_chunks_by_file:
            for c, v in old_chunks_by_file[rel]:
                new_chunks.append(c)
                new_vectors.append(v)
            n_reused += 1
            continue
        pending_chunks.extend(chunk_file(rel, text))

    print(f"扫描到 {n_files} 个文件，复用 {n_reused} 个，需要向量化 {len(pending_chunks)} 段", file=sys.stderr)
    if pending_chunks:
        vecs = embed_texts([embed_input_for_chunk(c) for c in pending_chunks])
        new_chunks.extend(pending_chunks)
        new_vectors.extend(list(vecs))

    if not new_chunks:
        sys.exit("没有可索引的内容（检查扩展名过滤或目录是否为空）")
    vectors = np.stack(new_vectors).astype(np.float32)
    save_index(index_dir, new_chunks, vectors, file_hashes, root)
    print(f"索引已保存到 {index_dir}：{len(new_chunks)} 段，维度 {vectors.shape[1]}", file=sys.stderr)


# ----------------------------------------------------------------------------
# 检索 + 生成
# ----------------------------------------------------------------------------


def retrieve(meta: dict, vectors_norm: np.ndarray, question: str, top_k: int, path_filter: Optional[str]) -> List[Tuple[float, dict]]:
    q = embed_texts([question])[0]
    q = q / (np.linalg.norm(q) or 1.0)
    scores = vectors_norm @ q
    order = np.argsort(-scores)
    results: List[Tuple[float, dict]] = []
    for idx in order:
        c = meta["chunks"][int(idx)]
        if path_filter and not fnmatch.fnmatch(c["file"], path_filter) and path_filter not in c["file"]:
            continue
        results.append((float(scores[idx]), c))
        if len(results) >= top_k:
            break
    return results


def build_context(results: List[Tuple[float, dict]], max_chars: int) -> str:
    parts: List[str] = []
    total = 0
    for i, (score, c) in enumerate(results, 1):
        block = f"[片段 {i}] {c['file']}:{c['start']}-{c['end']}  (相似度 {score:.3f})\n```\n{c['text']}\n```"
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def chat_stream(messages: List[dict], thinking: Optional[str]) -> str:
    """调用 /chat/completions（SSE 流式），边打印边返回完整回答。"""
    url = f"{CHAT_BASE_URL}/chat/completions"
    payload: dict = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
    }
    if thinking in ("on", "off"):
        payload["thinking"] = {"type": "enabled" if thinking == "on" else "disabled"}

    delay = 2.0
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, stream=True, timeout=(15, 300))
        except requests.RequestException as e:
            err = f"网络错误: {e}"
        else:
            if resp.status_code == 200:
                break
            err = f"HTTP {resp.status_code}: {resp.text[:500]}"
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise RuntimeError(f"对话请求失败：{err}")
        print(f"  [重试 {attempt}/3] {err}", file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    else:
        raise RuntimeError("对话请求多次失败")

    answer: List[str] = []
    in_reasoning = False
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        data = raw[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        reasoning = delta.get("reasoning_content")
        if reasoning:
            if not in_reasoning:
                print("\033[2m[思考] ", end="", flush=True)
                in_reasoning = True
            print(reasoning, end="", flush=True)
        content = delta.get("content")
        if content:
            if in_reasoning:
                print("\033[0m\n", flush=True)
                in_reasoning = False
            print(content, end="", flush=True)
            answer.append(content)
    if in_reasoning:
        print("\033[0m", flush=True)
    print()
    return "".join(answer)


def answer_question(meta: dict, vectors_norm: np.ndarray, question: str, args: argparse.Namespace,
                    history: List[dict]) -> None:
    results = retrieve(meta, vectors_norm, question, args.top_k, args.path)
    if not results:
        print("没有检索到相关片段。")
        return
    if args.show_chunks:
        print("--- 检索到的片段 ---", file=sys.stderr)
        for score, c in results:
            print(f"  {score:.3f}  {c['file']}:{c['start']}-{c['end']}", file=sys.stderr)
        print("--------------------", file=sys.stderr)
    context = build_context(results, args.max_context_chars)
    user_msg = (
        f"以下是从代码库 `{Path(meta['root']).name}` 中检索到的相关片段：\n\n{context}\n\n"
        f"问题：{question}"
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_msg}]
    answer = chat_stream(messages, args.thinking)
    # 多轮对话时，历史里只保留问题和回答，不重复塞代码片段，省 token
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    # 只保留最近 3 轮
    del history[:-6]


def cmd_ask(args: argparse.Namespace):
    meta, vectors = load_index(Path(args.index))
    if meta.get("embed_model") != EMBED_MODEL:
        print(f"警告：索引由 {meta.get('embed_model')} 生成，当前 ZHIPU_EMBED_MODEL={EMBED_MODEL}", file=sys.stderr)
    global EMBED_DIM
    EMBED_DIM = int(meta.get("dim", EMBED_DIM))  # 提问时的向量维度必须与索引一致
    vectors_norm = _normalize(vectors)
    history: List[dict] = []

    if args.question:
        answer_question(meta, vectors_norm, " ".join(args.question), args, history)
        return

    print(f"已加载索引：{len(meta['chunks'])} 段，来自 {meta['root']}")
    print("输入问题回车提问，输入 /reset 清空对话历史，Ctrl-D 或 /quit 退出。")
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("/quit", "/exit"):
            break
        if q == "/reset":
            history.clear()
            print("对话历史已清空。")
            continue
        try:
            answer_question(meta, vectors_norm, q, args, history)
        except RuntimeError as e:
            print(f"出错：{e}", file=sys.stderr)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="本地代码库 RAG 问答（智谱 embedding-3 + glm-5.3）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="扫描代码库并建立/更新向量索引")
    p_index.add_argument("repo", help="代码库根目录")
    p_index.add_argument("--index", default="./code_rag.index", help="索引保存目录（默认 ./code_rag.index）")
    p_index.add_argument("--ext", action="append", help="额外纳入的扩展名，可重复，如 --ext .tf")
    p_index.add_argument("--rebuild", action="store_true", help="忽略旧索引，全量重建")
    p_index.set_defaults(func=cmd_index)

    p_ask = sub.add_parser("ask", help="基于索引提问（不带问题则进入交互模式）")
    p_ask.add_argument("question", nargs="*", help="问题")
    p_ask.add_argument("--index", default="./code_rag.index", help="索引目录")
    p_ask.add_argument("--top-k", type=int, default=8, help="检索片段数（默认 8）")
    p_ask.add_argument("--path", help="只在路径包含/匹配该模式的文件中检索，如 --path 'src/api/*'")
    p_ask.add_argument("--max-context-chars", type=int, default=24000, help="塞给模型的上下文字符上限")
    p_ask.add_argument("--thinking", choices=["on", "off"], help="是否开启深度思考（不传则用服务端默认）")
    p_ask.add_argument("--show-chunks", action="store_true", help="打印命中的片段列表")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        sys.exit(f"出错：{e}")


if __name__ == "__main__":
    main()
