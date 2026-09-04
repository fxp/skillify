"""
查询：把问题向量化（Query 侧 instructions），与索引矩阵做余弦相似度，返回 top-k。

用法：
    export ARK_AGENT_PLAN_API_KEY=...
    python search.py "上季度会议里定的 OKR 是什么" --index index --top 5
    python search.py "登录页报错截图" --type image        # 只搜图片
    python search.py "..." --json                          # 机器可读输出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from ark_embedding import ArkEmbeddingError, embed_query, make_client


def load_index(index_dir: Path) -> tuple[dict[str, Any], np.ndarray]:
    meta_p, vec_p = index_dir / "meta.json", index_dir / "vectors.npy"
    if not meta_p.exists() or not vec_p.exists():
        raise SystemExit(f"索引不存在：{index_dir}，先运行 build_index.py")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    vectors = np.load(vec_p)
    if vectors.ndim != 2 or vectors.shape[0] != len(meta["items"]):
        raise SystemExit("索引损坏：vectors 与 meta.items 数量不一致，请 --rebuild")
    if vectors.shape[1] != meta["dimensions"]:
        raise SystemExit("索引损坏：vectors 维度与 meta.dimensions 不一致，请 --rebuild")
    return meta, vectors


def search(query: str, meta: dict[str, Any], vectors: np.ndarray,
           top_k: int = 5, type_filter: str | None = None) -> list[dict[str, Any]]:
    client = make_client()
    # 维度必须与建库一致，否则点积无意义
    res = embed_query(client, query, dimensions=int(meta["dimensions"]))
    if res.model != meta["model"]:
        # 官方要求 Query 与 Corpus 用同一模型版本；版本漂移时结果不可信
        print(f"[warn] 查询向量模型 {res.model} 与索引 {meta['model']} 不一致，建议重建索引",
              file=sys.stderr)

    # 索引行与查询向量都已 L2 归一化 -> 点积即余弦相似度
    scores = vectors @ res.vector
    if type_filter:
        mask = np.array([it["type"] == type_filter for it in meta["items"]])
        scores = np.where(mask, scores, -np.inf)

    k = min(top_k, int(np.isfinite(scores).sum()))
    if k <= 0:
        return []
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]

    results = []
    for rank, i in enumerate(idx, 1):
        it = meta["items"][int(i)]
        results.append({
            "rank": rank,
            "score": float(scores[i]),
            "type": it["type"],
            "source": it["source"],
            "heading": it["heading"],
            "preview": _preview(it["text"]),
        })
    return results


def _preview(text: str, limit: int = 160) -> str:
    body = text.split("\n\n", 1)[-1].replace("\n", " ").strip()
    return body if len(body) <= limit else body[:limit] + "…"


def main() -> None:
    ap = argparse.ArgumentParser(description="本地笔记 + 截图语义搜索")
    ap.add_argument("query")
    ap.add_argument("--index", type=Path, default=Path("index"))
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--type", choices=("text", "image"), default=None, help="只返回某一类结果")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    meta, vectors = load_index(args.index)
    try:
        results = search(args.query, meta, vectors, top_k=args.top, type_filter=args.type)
    except ArkEmbeddingError as e:
        raise SystemExit(f"[fatal] {e}") from e

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return
    if not results:
        print("无结果")
        return
    # 提示：跨模态相似度绝对值偏低是正常的（官方示例文搜图最佳匹配约 0.65），阈值按自己数据调
    for r in results:
        tag = "IMG " if r["type"] == "image" else "TXT "
        print(f"{r['rank']}. [{tag}{r['score']:.4f}] {r['source']}")
        print(f"     {r['heading']}")
        if r["preview"]:
            print(f"     {r['preview']}")


if __name__ == "__main__":
    main()
