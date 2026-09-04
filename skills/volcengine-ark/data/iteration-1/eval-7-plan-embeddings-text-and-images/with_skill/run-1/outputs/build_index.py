"""
建库：把 notes/*.md（按标题切块）和 imgs/*.png|jpg 向量化，存成 numpy 矩阵 + JSON 元数据。

用法：
    export ARK_AGENT_PLAN_API_KEY=...
    python build_index.py --notes notes --imgs imgs --out index
    python build_index.py --out index --rebuild        # 忽略缓存全量重算

产物：
    index/vectors.npy   float32 [N, dim]，每行已 L2 归一化（余弦相似度 = 点积）
    index/meta.json     {"model", "dimensions", "endpoint", "items": [...]}，items 与 vectors 行一一对应

增量：按 (source 路径, 内容 sha256) 复用旧向量，未变化的块 / 图不再请求。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

from ark_embedding import (
    ARK_PLAN_BASE_URL,
    DEFAULT_DIMENSIONS,
    EMBEDDING_MODEL,
    IMAGE_MIME_BY_SUFFIX,
    ArkEmbeddingError,
    embed_image,
    embed_note_chunk,
    estimate_afp,
    make_client,
    validate_image,
)

ENDPOINT = f"{ARK_PLAN_BASE_URL}/embeddings/multimodal"
MAX_CHUNK_CHARS = 1200          # 单块字符上限；模型上下文 128k 远够，切小是为了检索粒度
MIN_CHUNK_CHARS = 20            # 太短的碎片（只有一个标题）不单独入库


# --------------------------------------------------------------------------- 切块

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_markdown(text: str, title: str) -> list[dict[str, str]]:
    """
    按 Markdown 标题切成 section，超长 section 再按段落切。
    每块正文前面拼上「文件名 > 标题路径」作为上下文，便于跨块检索。
    返回 [{"heading": "...", "text": "..."}]。
    """
    sections: list[tuple[list[str], list[str]]] = []   # (heading_path, lines)
    heading_path: list[str] = []
    current: list[str] = []
    in_code = False

    def flush():
        if current:
            sections.append((list(heading_path), list(current)))
            current.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING_RE.match(line)
        if m:
            flush()
            level = len(m.group(1))
            heading_path = heading_path[: level - 1] + [m.group(2).strip()]
            continue
        current.append(line)
    flush()

    chunks: list[dict[str, str]] = []
    for path, lines in sections:
        body = "\n".join(lines).strip()
        if len(body) < MIN_CHUNK_CHARS:
            continue
        heading = " > ".join([title, *path])
        for piece in _split_long(body, MAX_CHUNK_CHARS):
            chunks.append({"heading": heading, "text": f"{heading}\n\n{piece}"})
    return chunks


def _split_long(body: str, limit: int) -> list[str]:
    if len(body) <= limit:
        return [body]
    pieces, buf = [], ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if len(para) > limit:                       # 单个巨型段落：硬切
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.extend(para[i : i + limit] for i in range(0, len(para), limit))
            continue
        if len(buf) + len(para) + 2 > limit and buf:
            pieces.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        pieces.append(buf)
    return pieces


# --------------------------------------------------------------------------- 收集素材

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect_items(notes_dir: Path | None, imgs_dir: Path | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if notes_dir and notes_dir.is_dir():
        for md in sorted(notes_dir.rglob("*.md")):
            text = md.read_text(encoding="utf-8", errors="replace")
            for i, ch in enumerate(chunk_markdown(text, md.stem)):
                items.append({
                    "id": f"note:{md.as_posix()}#{i}",
                    "type": "text",
                    "source": md.as_posix(),
                    "heading": ch["heading"],
                    "text": ch["text"],
                    "sha256": _sha256(ch["text"].encode("utf-8")),
                })
    if imgs_dir and imgs_dir.is_dir():
        for img in sorted(imgs_dir.rglob("*")):
            if not (img.is_file() and img.suffix.lower() in IMAGE_MIME_BY_SUFFIX):
                continue
            try:
                _, raw = validate_image(img)      # 大小 / 扩展名与真实格式一致性（方舟硬性要求）
            except ArkEmbeddingError as e:
                print(f"[skip] {e}", file=sys.stderr)   # 单张坏图不应中断整库构建
                continue
            items.append({
                "id": f"image:{img.as_posix()}",
                "type": "image",
                "source": img.as_posix(),
                "heading": img.name,
                "text": "",
                "sha256": _sha256(raw),
            })
    return items


# --------------------------------------------------------------------------- 主流程

def load_existing(out_dir: Path) -> tuple[dict[str, Any] | None, np.ndarray | None]:
    meta_p, vec_p = out_dir / "meta.json", out_dir / "vectors.npy"
    if meta_p.exists() and vec_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        vectors = np.load(vec_p)
        if vectors.shape[0] == len(meta.get("items", [])):
            return meta, vectors
        print("[warn] 旧索引 meta 与 vectors 行数不一致，忽略缓存", file=sys.stderr)
    return None, None


def build(notes_dir: Path | None, imgs_dir: Path | None, out_dir: Path,
          dimensions: int, workers: int, rebuild: bool) -> None:
    items = collect_items(notes_dir, imgs_dir)
    if not items:
        raise SystemExit("没有找到任何 .md 或图片，检查 --notes / --imgs 路径")
    n_text = sum(i["type"] == "text" for i in items)
    print(f"共 {len(items)} 条素材：{n_text} 个文本块，{len(items) - n_text} 张图片")

    # 复用缓存：同路径 + 同内容哈希 + 同维度 + 同模型版本
    cache: dict[tuple[str, str], np.ndarray] = {}
    old_model = None
    if not rebuild:
        old_meta, old_vecs = load_existing(out_dir)
        if old_meta and old_vecs is not None and old_meta.get("dimensions") == dimensions:
            old_model = old_meta.get("model")
            for row, it in zip(old_vecs, old_meta["items"]):
                cache[(it["source"], it["sha256"])] = row

    todo = [i for i in items if (i["source"], i["sha256"]) not in cache]
    print(f"需要请求 {len(todo)} 条，复用缓存 {len(items) - len(todo)} 条")

    client = make_client()
    vectors: dict[str, np.ndarray] = {}
    models_seen: set[str] = set()
    tok_text = tok_image = 0
    t0 = time.time()

    def work(it: dict[str, Any]):
        if it["type"] == "image":
            return it["id"], embed_image(client, it["source"], dimensions=dimensions)
        return it["id"], embed_note_chunk(client, it["text"], dimensions=dimensions)

    # 没有批量 endpoint：每条一次请求，用线程池并发（限流 429 会在 ark_embedding 里退避重试）
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, it) for it in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                item_id, res = fut.result()
            except ArkEmbeddingError as e:
                # 配置 / 额度类错误不可恢复：取消剩余任务，保留已完成的不写盘，直接退出
                for f in futures:
                    f.cancel()
                raise SystemExit(f"[fatal] {e}") from e
            vectors[item_id] = res.vector
            models_seen.add(res.model)
            tok_text += res.text_tokens
            tok_image += res.image_tokens
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}  已用 {time.time() - t0:.1f}s", flush=True)

    # 同一向量库不得混用模型版本（官方要求）；发现版本漂移时提示重建
    if len(models_seen) > 1:
        raise SystemExit(f"[fatal] 本次返回了多个模型版本 {models_seen}，请稍后重试或 --rebuild")
    model = next(iter(models_seen), old_model or EMBEDDING_MODEL)
    if old_model and models_seen and old_model != model:
        print(f"[warn] 服务端模型版本从 {old_model} 变为 {model}，缓存向量与新向量不同源，建议 --rebuild",
              file=sys.stderr)

    rows = []
    for it in items:
        v = vectors.get(it["id"])
        if v is None:
            v = cache[(it["source"], it["sha256"])]
        rows.append(v)
    matrix = np.stack(rows).astype(np.float32)

    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "vectors.npy", matrix)
    meta = {
        "endpoint": ENDPOINT,
        "model": model,
        "requested_model": EMBEDDING_MODEL,
        "dimensions": dimensions,
        "normalized": True,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "items": [{k: it[k] for k in ("id", "type", "source", "heading", "text", "sha256")} for it in items],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"完成：{matrix.shape[0]} 条 × {matrix.shape[1]} 维 -> {out_dir}/vectors.npy, meta.json")
    print(f"本次消耗 text_tokens={tok_text} image_tokens={tok_image}，"
          f"约 {estimate_afp(tok_text, tok_image):.2f} AFP（按向量化系数 0.5 估算）")


def main() -> None:
    ap = argparse.ArgumentParser(description="向量化 notes/*.md 与 imgs/*.png 建立本地语义索引")
    ap.add_argument("--notes", type=Path, default=Path("notes"), help="Markdown 笔记目录（递归）")
    ap.add_argument("--imgs", type=Path, default=Path("imgs"), help="图片目录（递归，png/jpg/webp/gif/bmp）")
    ap.add_argument("--out", type=Path, default=Path("index"), help="索引输出目录")
    ap.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS, choices=(1024, 2048))
    ap.add_argument("--workers", type=int, default=4, help="并发请求数")
    ap.add_argument("--rebuild", action="store_true", help="忽略已有索引缓存，全量重算")
    args = ap.parse_args()
    build(args.notes, args.imgs, args.out, args.dimensions, args.workers, args.rebuild)


if __name__ == "__main__":
    main()
