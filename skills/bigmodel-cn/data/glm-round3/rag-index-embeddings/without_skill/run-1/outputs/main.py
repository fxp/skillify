#!/usr/bin/env python3
"""最小 FAQ 检索：用智谱 embedding-3 建向量索引，余弦相似度取 top-3。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
QUERY = "发票怎么开"
TOP_K = 3
BATCH_SIZE = 64  # 官方限制：input 数组单次最多 64 条

BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def embed_texts(texts, api_key):
    """调用 embedding 接口向量化一批文本，返回与输入顺序一致的向量列表。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            API_URL,
            headers=headers,
            json={"model": MODEL, "input": batch},
            timeout=60,
        )
        if resp.status_code != 200:
            sys.exit(f"embedding 接口请求失败 HTTP {resp.status_code}：{resp.text}")
        data = sorted(resp.json()["data"], key=lambda item: item["index"])
        vectors.extend(item["embedding"] for item in data)
    return vectors


def cosine_similarity(a, b):
    """纯 Python 实现的余弦相似度（不依赖 numpy）。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    if not FAQ_PATH.exists():
        sys.exit(f"找不到 faq.txt（期望位于 {FAQ_PATH}）")
    faqs = [line.strip() for line in FAQ_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not faqs:
        sys.exit("faq.txt 里没有内容")

    # 1) 建索引：逐条向量化并落盘
    print(f"正在向量化 {len(faqs)} 条 FAQ ...", file=sys.stderr)
    faq_vectors = embed_texts(faqs, api_key)
    VECTORS_PATH.write_text(
        json.dumps(
            {"model": MODEL, "query": QUERY, "texts": faqs, "vectors": faq_vectors},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"向量索引已写入 {VECTORS_PATH}", file=sys.stderr)

    # 2) 检索：查询向量化 -> 余弦相似度 -> top-3
    query_vector = embed_texts([QUERY], api_key)[0]
    scored = sorted(
        ((cosine_similarity(query_vector, vec), text) for vec, text in zip(faq_vectors, faqs)),
        key=lambda pair: pair[0],
        reverse=True,
    )

    print(f"查询：{QUERY}")
    print(f"最相近的 top-{TOP_K}：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. {score:.4f}  {text}")


if __name__ == "__main__":
    main()
