#!/usr/bin/env python3
"""
本地代码库 RAG 问答（智谱 bigmodel.cn，纯 requests 直连 HTTP）

两套 Key、两个 Base URL，务必分开：
  - embedding-3   -> 标准 API      https://open.bigmodel.cn/api/paas/v4/embeddings
                     Key: ZHIPUAI_API_KEY（开放平台按量付费 Key）
                     ！GLM Coding Plan 套餐不包含 embeddings，套餐 Key 打这里会报 429/1113
  - glm-5.3 问答  -> Coding Plan   https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
                     Key: GLM_CODING_PLAN_API_KEY（套餐 Key）
  - rerank(可选)  -> 标准 API      https://open.bigmodel.cn/api/paas/v4/rerank（用 ZHIPUAI_API_KEY）

用法：
  export ZHIPUAI_API_KEY=...            # 标准 Key，做向量化 / rerank
  export GLM_CODING_PLAN_API_KEY=...    # 套餐 Key，做 glm-5.3 回答
  python3 code_rag.py index /path/to/repo                # 建索引（增量，按文件 hash 跳过未变更文件）
  python3 code_rag.py ask  /path/to/repo "这个项目的鉴权流程在哪里实现？"
  python3 code_rag.py ask  /path/to/repo "..." --rerank --stream --effort high
  python3 code_rag.py chat /path/to/repo                 # 交互式多轮问答

依赖：仅 requests（numpy 可选，有则加速相似度计算）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

try:  # numpy 可选
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

# --------------------------------------------------------------------------- #
# 常量：端点 / 模型
# --------------------------------------------------------------------------- #
STANDARD_BASE = "https://open.bigmodel.cn/api/paas/v4"          # 标准 API（embeddings / rerank）
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"     # GLM Coding Plan（对话）

EMBED_MODEL = "embedding-3"
EMBED_DIMENSIONS = 1024          # embedding-3 可选 256/512/1024/2048；索引与查询必须一致
EMBED_BATCH = 64                 # embedding-3 数组最多 64 条
EMBED_MAX_CHARS = 6000           # embedding-3 单条最多 3072 tokens，代码按 ~2 字符/token 保守截断

CHAT_MODEL = "glm-5.3"
RERANK_MODEL = "rerank"
RERANK_MAX_DOC_CHARS = 4096      # rerank 单条文档最长 4096 字符

INDEX_FILENAME = ".code_rag_index.json"

DEFAULT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".c", ".h",
    ".cpp", ".hpp", ".cc", ".cs", ".rb", ".php", ".swift", ".m", ".scala", ".sh",
    ".sql", ".proto", ".md", ".yaml", ".yml", ".toml", ".json", ".html", ".css", ".vue",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "target", ".venv", "venv",
    "__pycache__", ".idea", ".vscode", ".next", ".cache", "vendor", ".mypy_cache",
}
MAX_FILE_BYTES = 512 * 1024


# --------------------------------------------------------------------------- #
# HTTP：统一的带退避重试的 POST
# --------------------------------------------------------------------------- #
class ApiError(RuntimeError):
    pass


def _explain_error(resp: requests.Response, base: str) -> str:
    """把智谱的业务错误码翻译成人话，尤其是 1113 这个 Coding Plan 常见坑。"""
    try:
        body = resp.json()
        err = body.get("error", {}) if isinstance(body, dict) else {}
        code, msg = str(err.get("code", "")), err.get("message", "")
    except Exception:
        code, msg = "", resp.text[:300]

    hint = ""
    if code == "1113":
        if base == STANDARD_BASE:
            hint = (
                "\n  提示：1113 = 该 Key 对应的账户没有余额/资源包。这是标准 API 端点，"
                "只认开放平台按量付费 Key（ZHIPUAI_API_KEY）。\n"
                "  如果你把 Coding Plan 套餐 Key 填进了 ZHIPUAI_API_KEY，会得到这个错——"
                "套餐不包含 embeddings / rerank，需要单独的标准 Key 并有少量余额。"
            )
        else:
            hint = "\n  提示：Coding 端点报 1113，请确认 GLM_CODING_PLAN_API_KEY 是套餐 Key 且套餐未过期。"
    elif code in ("1000", "1001", "1003"):
        hint = "\n  提示：鉴权失败，检查 Authorization: Bearer <KEY> 是否正确、Key 是否属于对应体系。"
    elif code == "1211":
        hint = "\n  提示：模型不存在，检查 model 拼写。"
    elif code in ("1308", "1310"):
        hint = "\n  提示：达到用量上限（套餐 5 小时/7 天额度或账户配额），等待重置后再试。"
    return f"HTTP {resp.status_code} code={code} message={msg}{hint}"


def post_json(url: str, api_key: str, payload: dict, *, base: str,
              stream: bool = False, timeout: int = 300, max_retries: int = 5) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, stream=stream, timeout=timeout)
        except requests.RequestException as e:
            last_err = f"network error: {e}"
            resp = None
        if resp is not None:
            if resp.status_code < 400:
                return resp
            last_err = _explain_error(resp, base)
            # 4xx（除 429）是配置/参数问题，重试无意义
            if resp.status_code != 429 and resp.status_code < 500:
                raise ApiError(f"{url}\n  {last_err}")
            # 429 且是 1113（余额/套餐问题）也不值得重试
            if "code=1113" in last_err:
                raise ApiError(f"{url}\n  {last_err}")
        if attempt == max_retries:
            break
        sleep = min(2 ** attempt, 30) + random.uniform(0, 1)   # 指数退避 + 抖动
        print(f"[retry {attempt + 1}/{max_retries}] {last_err.splitlines()[0]} -> {sleep:.1f}s", file=sys.stderr)
        time.sleep(sleep)
    raise ApiError(f"{url}\n  重试耗尽：{last_err}")


# --------------------------------------------------------------------------- #
# Key 读取
# --------------------------------------------------------------------------- #
def get_standard_key() -> str:
    key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not key:
        sys.exit(
            "缺少环境变量 ZHIPUAI_API_KEY（开放平台标准 API Key）。\n"
            "embedding-3 / rerank 不在 GLM Coding Plan 套餐内，必须用标准 Key：\n"
            "  https://bigmodel.cn/usercenter/proj-mgmt/apikeys"
        )
    return key


def get_coding_plan_key() -> str:
    key = os.environ.get("GLM_CODING_PLAN_API_KEY", "").strip()
    if not key:
        sys.exit(
            "缺少环境变量 GLM_CODING_PLAN_API_KEY（GLM Coding Plan 套餐 Key）。\n"
            "个人版在 https://bigmodel.cn/coding-plan/personal/overview 新建。"
        )
    return key


# --------------------------------------------------------------------------- #
# 代码切片
# --------------------------------------------------------------------------- #
def iter_source_files(root: Path, exts: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in exts:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def chunk_lines(lines: list[str], chunk_lines_n: int, overlap: int) -> Iterable[tuple[int, int, str]]:
    """按行滑窗切片，返回 (start_line, end_line, text)，行号从 1 开始。"""
    if not lines:
        return
    step = max(1, chunk_lines_n - overlap)
    i = 0
    n = len(lines)
    while i < n:
        j = min(n, i + chunk_lines_n)
        text = "".join(lines[i:j])
        if text.strip():
            yield i + 1, j, text
        if j >= n:
            break
        i += step


def file_sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 16), b""):
            h.update(blk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Embeddings（标准 API，标准 Key）
# --------------------------------------------------------------------------- #
def embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """按 64 条一批调用 embedding-3，按返回的 index 对齐结果。"""
    out: list[list[float] | None] = [None] * len(texts)
    for s in range(0, len(texts), EMBED_BATCH):
        batch = [t[:EMBED_MAX_CHARS] for t in texts[s:s + EMBED_BATCH]]
        resp = post_json(
            f"{STANDARD_BASE}/embeddings",
            api_key,
            {"model": EMBED_MODEL, "input": batch, "dimensions": EMBED_DIMENSIONS},
            base=STANDARD_BASE,
            timeout=120,
        )
        data = resp.json()
        for item in data["data"]:
            out[s + item["index"]] = item["embedding"]   # 不假设返回顺序，按 index 对齐
        usage = data.get("usage", {})
        print(f"  embedded {s + len(batch)}/{len(texts)}  (tokens={usage.get('total_tokens')})", file=sys.stderr)
    if any(v is None for v in out):
        raise ApiError("embeddings 返回缺少部分 index")
    return out  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# 索引
# --------------------------------------------------------------------------- #
def load_index(root: Path) -> dict:
    p = root / INDEX_FILENAME
    if p.exists():
        with open(p, encoding="utf-8") as f:
            idx = json.load(f)
        if idx.get("model") != EMBED_MODEL or idx.get("dimensions") != EMBED_DIMENSIONS:
            print("索引的 model/dimensions 与当前配置不一致，将重建索引。", file=sys.stderr)
            return {"model": EMBED_MODEL, "dimensions": EMBED_DIMENSIONS, "files": {}, "chunks": []}
        return idx
    return {"model": EMBED_MODEL, "dimensions": EMBED_DIMENSIONS, "files": {}, "chunks": []}


def save_index(root: Path, idx: dict) -> None:
    tmp = root / (INDEX_FILENAME + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    tmp.replace(root / INDEX_FILENAME)


def build_index(root: Path, chunk_n: int, overlap: int, exts: set[str], rebuild: bool) -> None:
    api_key = get_standard_key()
    idx = load_index(root) if not rebuild else {
        "model": EMBED_MODEL, "dimensions": EMBED_DIMENSIONS, "files": {}, "chunks": []
    }
    old_files: dict = idx["files"]
    kept_chunks: list[dict] = []
    new_files: dict = {}
    pending: list[dict] = []

    current = {}
    for p in iter_source_files(root, exts):
        rel = str(p.relative_to(root))
        try:
            sha = file_sha1(p)
        except OSError:
            continue
        current[rel] = sha

    # 未变更文件：保留旧向量
    for c in idx["chunks"]:
        if c["path"] in current and old_files.get(c["path"]) == current[c["path"]]:
            kept_chunks.append(c)
    for rel, sha in current.items():
        if old_files.get(rel) == sha:
            new_files[rel] = sha
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines(keepends=True)
        for start, end, body in chunk_lines(lines, chunk_n, overlap):
            pending.append({"path": rel, "start": start, "end": end, "text": body})
        new_files[rel] = sha

    removed = [r for r in old_files if r not in current]
    print(f"文件总数 {len(current)}，需要重新向量化的切片 {len(pending)}，"
          f"复用旧切片 {len(kept_chunks)}，删除的文件 {len(removed)}", file=sys.stderr)

    if pending:
        # 给每个切片加上路径前缀再向量化，让向量带上文件位置语义
        texts = [f"// file: {c['path']} (L{c['start']}-L{c['end']})\n{c['text']}" for c in pending]
        vecs = embed_texts(texts, api_key)
        for c, v in zip(pending, vecs):
            c["vec"] = v
    idx["files"] = new_files
    idx["chunks"] = kept_chunks + pending
    save_index(root, idx)
    print(f"索引已写入 {root / INDEX_FILENAME}，共 {len(idx['chunks'])} 个切片。", file=sys.stderr)


# --------------------------------------------------------------------------- #
# 检索
# --------------------------------------------------------------------------- #
def cosine_topk(query_vec: list[float], chunks: list[dict], k: int) -> list[tuple[float, dict]]:
    if np is not None:
        m = np.asarray([c["vec"] for c in chunks], dtype=np.float32)
        q = np.asarray(query_vec, dtype=np.float32)
        m_norm = np.linalg.norm(m, axis=1) + 1e-9
        scores = (m @ q) / (m_norm * (np.linalg.norm(q) + 1e-9))
        order = np.argsort(-scores)[:k]
        return [(float(scores[i]), chunks[i]) for i in order]
    qn = math.sqrt(sum(x * x for x in query_vec)) + 1e-9
    scored = []
    for c in chunks:
        v = c["vec"]
        dot = sum(a * b for a, b in zip(v, query_vec))
        vn = math.sqrt(sum(a * a for a in v)) + 1e-9
        scored.append((dot / (vn * qn), c))
    scored.sort(key=lambda t: -t[0])
    return scored[:k]


def rerank(query: str, candidates: list[dict], api_key: str, top_n: int) -> list[dict]:
    """标准 API 的 rerank 精排（可选）。documents 最多 128 条、单条 4096 字符。"""
    docs = [f"{c['path']} L{c['start']}-{c['end']}\n{c['text']}"[:RERANK_MAX_DOC_CHARS] for c in candidates[:128]]
    resp = post_json(
        f"{STANDARD_BASE}/rerank",
        api_key,
        {"model": RERANK_MODEL, "query": query[:4096], "documents": docs, "top_n": top_n},
        base=STANDARD_BASE,
        timeout=60,
    )
    results = resp.json()["results"]
    out = []
    for r in results:
        c = dict(candidates[r["index"]])
        c["score"] = r.get("relevance_score")
        out.append(c)
    return out


def retrieve(root: Path, query: str, top_k: int, recall_k: int, use_rerank: bool) -> list[dict]:
    idx = load_index(root)
    if not idx["chunks"]:
        sys.exit(f"索引为空，请先运行: python3 code_rag.py index {root}")
    std_key = get_standard_key()
    qvec = embed_texts([query], std_key)[0]           # 查询向量必须用同一 model + dimensions
    hits = cosine_topk(qvec, idx["chunks"], recall_k if use_rerank else top_k)
    cands = []
    for score, c in hits:
        cc = {k: v for k, v in c.items() if k != "vec"}
        cc["score"] = score
        cands.append(cc)
    if use_rerank:
        cands = rerank(query, cands, std_key, top_n=top_k)
    return cands


# --------------------------------------------------------------------------- #
# 生成（Coding Plan 端点，套餐 Key）
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = (
    "你是一个代码库问答助手。只依据下面提供的代码片段回答用户问题；"
    "引用代码时标明文件路径和行号（如 `src/auth.py L12-L40`）。"
    "如果片段不足以回答，请明确说明缺少哪些信息，不要编造。用中文回答。"
)


def build_context(chunks: list[dict], max_chars: int) -> str:
    parts, used = [], 0
    for c in chunks:
        block = f"### {c['path']} (L{c['start']}-L{c['end']})\n```\n{c['text'].rstrip()}\n```\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def chat_completion(messages: list[dict], api_key: str, *, effort: str, max_tokens: int, stream: bool) -> str:
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        # glm-5.3 强制思考、不能关闭（传 thinking.type=disabled 会报 1210）；只能用 reasoning_effort 调强度。
        # 套餐额度按输出 token ×24 计，代码问答默认 low 更省额度。
        "reasoning_effort": effort,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": stream,
    }
    url = f"{CODING_BASE}/chat/completions"
    if not stream:
        resp = post_json(url, api_key, payload, base=CODING_BASE)
        data = resp.json()
        choice = data["choices"][0]
        fr = choice.get("finish_reason")
        if fr not in (None, "stop"):
            print(f"[warn] finish_reason={fr}", file=sys.stderr)
        usage = data.get("usage", {})
        print(f"[usage] prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')}",
              file=sys.stderr)
        return choice["message"].get("content") or ""

    # SSE 流式：逐行解析 data: {...}，以 data: [DONE] 结束；异常只体现在 finish_reason 里
    resp = post_json(url, api_key, payload, base=CODING_BASE, stream=True)
    buf: list[str] = []
    finish_reason = None
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        data_str = raw[5:].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {}) or {}
        piece = delta.get("content")
        if piece:
            buf.append(piece)
            sys.stdout.write(piece)
            sys.stdout.flush()
        if choices[0].get("finish_reason"):
            finish_reason = choices[0]["finish_reason"]
        if chunk.get("usage"):
            u = chunk["usage"]
            print(f"\n[usage] prompt={u.get('prompt_tokens')} completion={u.get('completion_tokens')}",
                  file=sys.stderr)
    sys.stdout.write("\n")
    if finish_reason not in (None, "stop"):
        print(f"[warn] finish_reason={finish_reason}", file=sys.stderr)
    return "".join(buf)


def answer(root: Path, question: str, history: list[dict], args) -> str:
    chunks = retrieve(root, question, args.top_k, args.recall_k, args.rerank)
    print("检索到的片段：", file=sys.stderr)
    for c in chunks:
        print(f"  {c['score']:.3f}  {c['path']} L{c['start']}-L{c['end']}", file=sys.stderr)
    context = build_context(chunks, args.max_context_chars)
    user_msg = f"相关代码片段：\n\n{context}\n\n问题：{question}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_msg}]
    reply = chat_completion(messages, get_coding_plan_key(),
                            effort=args.effort, max_tokens=args.max_tokens, stream=args.stream)
    # 多轮历史里只保留问题本身，不保留大段上下文，避免上下文膨胀烧额度
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply})
    return reply


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="本地代码库 RAG 问答（embedding-3 + glm-5.3）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index", help="建立/更新向量索引（用标准 Key 调 embedding-3）")
    p_idx.add_argument("repo")
    p_idx.add_argument("--chunk-lines", type=int, default=60, help="每个切片的行数（默认 60）")
    p_idx.add_argument("--overlap", type=int, default=10, help="切片重叠行数（默认 10）")
    p_idx.add_argument("--ext", action="append", help="额外纳入的扩展名，如 --ext .lua，可重复")
    p_idx.add_argument("--rebuild", action="store_true", help="忽略旧索引全部重建")

    def add_ask_args(p):
        p.add_argument("repo")
        p.add_argument("--top-k", type=int, default=8, help="送入模型的片段数（默认 8）")
        p.add_argument("--recall-k", type=int, default=30, help="开启 rerank 时向量召回数（默认 30）")
        p.add_argument("--rerank", action="store_true", help="用标准 API 的 rerank 做精排")
        p.add_argument("--effort", choices=["low", "high", "max"], default="low",
                       help="glm-5.3 的 reasoning_effort（默认 low，最省套餐额度）")
        p.add_argument("--max-tokens", type=int, default=4096)
        p.add_argument("--max-context-chars", type=int, default=40000)
        p.add_argument("--stream", action="store_true", help="流式输出")

    p_ask = sub.add_parser("ask", help="单次提问")
    add_ask_args(p_ask)
    p_ask.add_argument("question")

    p_chat = sub.add_parser("chat", help="交互式多轮问答")
    add_ask_args(p_chat)

    args = ap.parse_args()
    root = Path(args.repo).resolve()
    if not root.is_dir():
        sys.exit(f"目录不存在: {root}")

    if args.cmd == "index":
        exts = set(DEFAULT_EXTS) | {e if e.startswith(".") else "." + e for e in (args.ext or [])}
        build_index(root, args.chunk_lines, args.overlap, exts, args.rebuild)
        return

    history: list[dict] = []
    if args.cmd == "ask":
        reply = answer(root, args.question, history, args)
        if not args.stream:
            print(reply)
        return

    print("进入多轮问答，输入 exit 退出。", file=sys.stderr)
    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("exit", "quit"):
            break
        try:
            reply = answer(root, q, history, args)
            if not args.stream:
                print(reply)
        except ApiError as e:
            print(f"[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        sys.exit(f"[error] {e}")
