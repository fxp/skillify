"""构建 / 增量更新本地向量索引。

用法：
    python indexer.py            # 增量：只处理新增或修改过的文件
    python indexer.py --rebuild  # 全量重建

索引落盘在 INDEX_DIR：
    embeddings.npy  float32, shape=(N, dim)，已 L2 归一化
    meta.json       与行号一一对应的元数据 + 文件指纹（用于增量）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ark_embeddings import ArkEmbedder
from config import Settings

log = logging.getLogger("indexer")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@dataclass
class Item:
    kind: str          # "note" | "image"
    source: str        # 相对路径
    chunk: int         # 文本块序号；图片恒为 0
    preview: str       # 用于展示的片段（图片则是文件名）
    fingerprint: str   # 文件内容 sha1（增量判断）


def file_fingerprint(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """先按空行分段，再把段落贪心合并到 size 字以内；超长段按字符切并保留 overlap。"""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(p) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            step = max(1, size - overlap)
            for i in range(0, len(p), step):
                chunks.append(p[i : i + size])
            continue
        if len(buf) + len(p) + 2 <= size:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    if not chunks and text.strip():
        chunks.append(text.strip()[:size])
    return chunks


class Index:
    def __init__(self, index_dir: Path):
        self.dir = index_dir
        self.vec_path = index_dir / "embeddings.npy"
        self.meta_path = index_dir / "meta.json"
        self.vectors = np.zeros((0, 0), dtype=np.float32)
        self.items: list[Item] = []
        self.model = ""

    def load(self) -> "Index":
        if self.vec_path.exists() and self.meta_path.exists():
            self.vectors = np.load(self.vec_path)
            meta = json.loads(self.meta_path.read_text("utf-8"))
            self.model = meta.get("model", "")
            self.items = [Item(**it) for it in meta["items"]]
        return self

    def save(self, model: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        np.save(self.vec_path, self.vectors.astype(np.float32))
        self.meta_path.write_text(
            json.dumps(
                {"model": model, "dim": int(self.vectors.shape[1]) if self.vectors.size else 0,
                 "items": [asdict(i) for i in self.items]},
                ensure_ascii=False, indent=1,
            ),
            "utf-8",
        )

    def drop_source(self, source: str) -> None:
        keep = [i for i, it in enumerate(self.items) if it.source != source]
        if len(keep) != len(self.items):
            self.vectors = self.vectors[keep] if self.vectors.size else self.vectors
            self.items = [self.items[i] for i in keep]

    def append(self, vecs: np.ndarray, items: list[Item]) -> None:
        if len(items) == 0:
            return
        assert vecs.shape[0] == len(items)
        if self.vectors.size == 0:
            self.vectors = vecs
        else:
            if self.vectors.shape[1] != vecs.shape[1]:
                raise RuntimeError(
                    f"维度不一致：已有索引 {self.vectors.shape[1]}，新向量 {vecs.shape[1]}。请 --rebuild。"
                )
            self.vectors = np.vstack([self.vectors, vecs])
        self.items.extend(items)

    def fingerprints(self) -> dict[str, str]:
        return {it.source: it.fingerprint for it in self.items}


def build(settings: Settings, rebuild: bool = False) -> None:
    embedder = ArkEmbedder(settings)
    index = Index(settings.index_dir)
    if not rebuild:
        index.load()
        if index.model and index.model != settings.model:
            log.warning("索引由模型 %s 构建，当前模型 %s，强制全量重建。", index.model, settings.model)
            index = Index(settings.index_dir)
    known = index.fingerprints()
    cwd = Path.cwd()

    # ---- 笔记
    notes = sorted(settings.notes_dir.glob("*.md")) if settings.notes_dir.exists() else []
    seen_sources: set[str] = set()
    for path in notes:
        rel = str(path.relative_to(cwd)) if path.is_absolute() else str(path)
        seen_sources.add(rel)
        fp = file_fingerprint(path)
        if known.get(rel) == fp:
            continue
        text = path.read_text("utf-8", errors="replace")
        chunks = chunk_text(text, settings.chunk_chars, settings.chunk_overlap)
        if not chunks:
            log.info("跳过空文件 %s", rel)
            continue
        # 把文件名作为前缀带进去，让标题信息参与向量化
        payloads = [f"{path.stem}\n\n{c}" for c in chunks]
        log.info("向量化 %s（%d 块）", rel, len(chunks))
        vecs = embedder.embed_texts(payloads)
        index.drop_source(rel)
        index.append(
            vecs,
            [Item("note", rel, i, c[:120].replace("\n", " "), fp) for i, c in enumerate(chunks)],
        )

    # ---- 图片
    images = (
        sorted(p for p in settings.images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if settings.images_dir.exists() else []
    )
    if images and not settings.supports_images:
        log.warning("EMBED_BACKEND=text，跳过 %d 张图片。切换 EMBED_BACKEND=multimodal 可入库。", len(images))
        images = []
    for path in images:
        rel = str(path)
        seen_sources.add(rel)
        fp = file_fingerprint(path)
        if known.get(rel) == fp:
            continue
        log.info("向量化图片 %s", rel)
        # 文件名常带语义（如 2024-会议纪要.png），作为 caption 一起融合
        vec = embedder.embed_image(path, caption=path.stem)
        index.drop_source(rel)
        index.append(vec[None, :], [Item("image", rel, 0, path.name, fp)])

    # ---- 删除已不存在的文件
    for src in list(known):
        if src not in seen_sources:
            log.info("移除已删除文件 %s", src)
            index.drop_source(src)

    index.save(settings.model)
    log.info("索引完成：%d 条向量，维度 %s，模型 %s，保存于 %s",
             len(index.items), index.vectors.shape[1] if index.vectors.size else 0,
             settings.model, settings.index_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description="构建本地笔记/截图向量索引")
    ap.add_argument("--rebuild", action="store_true", help="忽略已有索引，全量重建")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    build(Settings(), rebuild=args.rebuild)
    return 0


if __name__ == "__main__":
    sys.exit(main())
