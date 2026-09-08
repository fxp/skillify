#!/usr/bin/env python3
"""最小语义检索：用智谱 embedding-3 把 faq.txt 的每一行向量化，存成同目录的
vectors.json，然后对固定查询「发票怎么开」算余弦相似度取 top-3 打印原文。

只依赖 requests（向量运算手写，不用 numpy）。
用法: ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import math
import os
from pathlib import Path

import requests

EMBEDDINGS_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # embedding-3 支持 256/512/1024/2048；建索引和查询必须用同一 model+dimensions 组合
BATCH_SIZE = 64    # 官方限制：input 数组单次最多 64 条
QUERY = "发票怎么开"
TOP_K = 3

BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def embed_texts(api_key, texts):
    """把一批文本向量化：按 BATCH_SIZE 分批调用 API，并按响应里的 index 对齐回输入顺序。"""
    vectors = [None] * len(texts)
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": MODEL, "input": batch, "dimensions": DIMENSIONS},
            timeout=60,
        )
        if resp.status_code != 200:
            # 失败时官方返回 error.code / error.message，原样带出来便于排查
            raise SystemExit(f"embeddings 调用失败 HTTP {resp.status_code}: {resp.text}")
        for item in resp.json()["data"]:
            vectors[start + item["index"]] = item["embedding"]
    missing = [i for i, v in enumerate(vectors) if v is None]
    if missing:
        raise SystemExit(f"API 未返回全部向量，缺少输入下标: {missing}")
    return vectors


def cosine_similarity(vec_a, vec_b):
    dot = norm_a = norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise SystemExit("缺少环境变量 ZHIPUAI_API_KEY，请先设置再运行。")

    if not FAQ_PATH.is_file():
        raise SystemExit(f"找不到 {FAQ_PATH}，请把 faq.txt 和 main.py 放在同一目录。")

    faqs = [line.strip() for line in FAQ_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not faqs:
        raise SystemExit(f"{FAQ_PATH} 中没有读到任何问题。")
    print(f"从 {FAQ_PATH.name} 读取 {len(faqs)} 条 FAQ，开始向量化（每批最多 {BATCH_SIZE} 条）……")

    vectors = embed_texts(api_key, faqs)

    index = {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "vectors": [{"text": text, "embedding": vec} for text, vec in zip(faqs, vectors)],
    }
    VECTORS_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"向量索引已写入 {VECTORS_PATH}")

    query_vec = embed_texts(api_key, [QUERY])[0]
    scored = sorted(
        ((cosine_similarity(query_vec, vec), text) for text, vec in zip(faqs, vectors)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    print(f'\n查询: "{QUERY}"')
    print(f"最相近的 Top-{TOP_K}:")
    for rank, (score, text) in enumerate(scored[:TOP_K], start=1):
        print(f"{rank}. (相似度 {score:.4f}) {text}")


if __name__ == "__main__":
    main()
