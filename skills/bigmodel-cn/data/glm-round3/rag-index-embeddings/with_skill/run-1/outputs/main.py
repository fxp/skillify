# -*- coding: utf-8 -*-
"""最小可用的 FAQ 语义检索。

流程：读 faq.txt -> 分批调智谱 embedding-3 向量化 -> 存 vectors.json
     -> 用「发票怎么开」算余弦相似度 -> 打印 top-3 原文。

运行：ZHIPUAI_API_KEY=... python3 main.py
依赖：仅 requests（相似度用纯 Python 计算，不用 numpy）。
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # embedding-3 支持 256/512/1024/2048；建库与查询必须同 model+dimensions
BATCH_SIZE = 64  # 官方限制：input 数组单次最多 64 条，150 条必须分批发
QUERY = "发票怎么开"

BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def embed_texts(texts, api_key):
    """调 embeddings 接口把一批文本（不超过 64 条）转成向量，按 index 对齐后返回。"""
    last_error = None
    for attempt in range(3):  # 瞬时网络错误做简单重试
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": MODEL, "input": texts, "dimensions": DIMENSIONS},
                timeout=60,
            )
            resp.raise_for_status()
            items = sorted(resp.json()["data"], key=lambda d: d["index"])
            return [item["embedding"] for item in items]
        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    sys.exit(f"embeddings 调用失败: {last_error}")


def cosine(a, b):
    """纯 Python 计算两个向量的余弦相似度。"""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("缺少 API Key：请先设置环境变量 ZHIPUAI_API_KEY")

    if not FAQ_PATH.exists():
        sys.exit(f"找不到 {FAQ_PATH}")

    faq_lines = [ln.strip() for ln in FAQ_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"读取 faq.txt：{len(faq_lines)} 条")

    # 分批向量化，避免超过单次 64 条的数组上限
    vectors = []
    for start in range(0, len(faq_lines), BATCH_SIZE):
        batch = faq_lines[start : start + BATCH_SIZE]
        vectors.extend(embed_texts(batch, api_key))
        print(f"向量化进度 {min(start + BATCH_SIZE, len(faq_lines))}/{len(faq_lines)}")

    VECTORS_PATH.write_text(
        json.dumps(
            {"model": MODEL, "dimensions": DIMENSIONS, "texts": faq_lines, "vectors": vectors},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"已写入 {VECTORS_PATH.name}（{len(vectors)} 条 {len(vectors[0])} 维向量）")

    # 查询向量化：同一 model + dimensions，保证向量空间一致
    query_vec = embed_texts([QUERY], api_key)[0]

    scored = sorted(
        ((cosine(query_vec, vec), text) for text, vec in zip(faq_lines, vectors)),
        key=lambda pair: pair[0],
        reverse=True,
    )

    print(f"\n查询：{QUERY}")
    print("Top-3 最相似的常见问题：")
    for rank, (score, text) in enumerate(scored[:3], 1):
        print(f"{rank}. {text}（相似度 {score:.4f}）")


if __name__ == "__main__":
    main()
