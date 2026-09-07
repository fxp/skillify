"""最小可用的 FAQ 语义检索。

流程：读同目录 faq.txt -> 用智谱 embedding-3 分批向量化 -> 存 vectors.json
     -> 用「发票怎么开」做查询，算余弦相似度取 top-3，打印原文。

依赖：仅 requests（余弦相似度纯手算，不用 numpy）。
运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"

EMBEDDINGS_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # 可选 256/512/1024/2048；索引与查询必须用同一 model+dimensions
BATCH_SIZE = 64    # embedding-3 的 input 数组单次最多 64 条
QUERY = "发票怎么开"
TOP_K = 3


def embed(texts):
    """把一组文本向量化，按响应里的 index 对齐，返回与输入同序的向量列表。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    vectors = [None] * len(texts)
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL, "input": batch, "dimensions": DIMENSIONS},
            timeout=60,
        )
        if resp.status_code != 200:
            sys.exit(f"embeddings 接口报错 HTTP {resp.status_code}: {resp.text}")
        for item in resp.json()["data"]:
            vectors[start + item["index"]] = item["embedding"]
    return vectors


def cosine(a, b):
    """纯 Python 计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    if not FAQ_PATH.exists():
        sys.exit(f"找不到 {FAQ_PATH}，请把 faq.txt 放在脚本同目录下")
    faqs = [line.strip() for line in FAQ_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not faqs:
        sys.exit("faq.txt 是空的")
    print(f"从 faq.txt 读到 {len(faqs)} 条 FAQ，开始向量化…")

    vectors = embed(faqs)
    VECTORS_PATH.write_text(
        json.dumps(
            {"model": MODEL, "dimensions": DIMENSIONS, "texts": faqs, "vectors": vectors},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"向量已写入 {VECTORS_PATH}")

    query_vec = embed([QUERY])[0]
    scores = [cosine(query_vec, v) for v in vectors]
    top = sorted(range(len(faqs)), key=lambda i: scores[i], reverse=True)[:TOP_K]

    print(f"\n查询：{QUERY}")
    print(f"最相近的 Top {TOP_K}：")
    for rank, i in enumerate(top, 1):
        print(f"{rank}. {faqs[i]}   (相似度 {scores[i]:.4f})")


if __name__ == "__main__":
    main()
