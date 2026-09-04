"""对索引做语义检索。

用法：
    python search.py "上季度 OKR 复盘"            # top5
    python search.py -k 10 --by-file "部署流程"    # 按文件聚合
    python search.py --image imgs/xxx.png         # 以图搜图/搜文（需 multimodal 后端）
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

from ark_embeddings import ArkEmbedder
from config import Settings
from indexer import Index, Item


def search(query_vec: np.ndarray, index: Index, k: int = 5, by_file: bool = False) -> list[tuple[float, Item]]:
    """query_vec 与索引向量均已 L2 归一化，点积即余弦相似度。"""
    if index.vectors.size == 0:
        return []
    q = np.asarray(query_vec, dtype=np.float32).ravel()
    if q.shape[0] != index.vectors.shape[1]:
        raise RuntimeError(f"查询维度 {q.shape[0]} 与索引维度 {index.vectors.shape[1]} 不一致，请重建索引。")
    scores = index.vectors @ q  # shape=(N,)

    if not by_file:
        top = np.argsort(-scores)[:k]
        return [(float(scores[i]), index.items[i]) for i in top]

    # 每个文件取最高分的块作为代表
    best: dict[str, tuple[float, Item]] = {}
    for i, it in enumerate(index.items):
        s = float(scores[i])
        if it.source not in best or s > best[it.source][0]:
            best[it.source] = (s, it)
    return sorted(best.values(), key=lambda t: -t[0])[:k]


def main() -> int:
    ap = argparse.ArgumentParser(description="本地笔记语义搜索")
    ap.add_argument("query", nargs="?", help="查询文本")
    ap.add_argument("--image", type=Path, help="用一张图片作为查询（可与 query 同时给出，图文融合）")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--by-file", action="store_true", help="按文件聚合，每个文件只显示最相关的一块")
    ap.add_argument("--min-score", type=float, default=None, help="过滤低于该余弦分数的结果")
    args = ap.parse_args()
    if not args.query and not args.image:
        ap.error("请提供查询文本或 --image")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    settings = Settings()
    index = Index(settings.index_dir).load()
    if not index.items:
        print(f"索引为空，请先运行 python indexer.py（目录 {settings.index_dir}）", file=sys.stderr)
        return 1

    embedder = ArkEmbedder(settings)
    if args.image:
        qv = embedder.embed_image(args.image, caption=args.query)
    else:
        qv = embedder.embed_texts([args.query])[0]

    results = search(qv, index, k=args.k, by_file=args.by_file)
    if args.min_score is not None:
        results = [r for r in results if r[0] >= args.min_score]

    if not results:
        print("没有结果。")
        return 0
    for rank, (score, it) in enumerate(results, 1):
        tag = "IMG " if it.kind == "image" else f"#{it.chunk:<3}"
        print(f"{rank}. [{score:.4f}] {tag} {it.source}")
        if it.kind == "note":
            print(f"      {it.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
