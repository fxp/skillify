"""最小 FAQ 语义检索：用智谱 embedding-3 建索引，余弦相似度取 top-3。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

流程：
    1. 读取同目录 faq.txt（每行一条 FAQ）
    2. 调 embedding-3 分批向量化（单次 input 数组最多 64 条），结果存入同目录 vectors.json
    3. 用「发票怎么开」做查询，手写余弦相似度，把最相近的 3 条原文打印到 stdout
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

EMBEDDINGS_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # embedding-3 支持 256/512/1024/2048；索引与查询必须用同一维度
BATCH_SIZE = 64    # 官方限制：input 数组一次最多 64 条
QUERY = "发票怎么开"
TOP_K = 3

BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def embed(texts, api_key):
    """调用 embedding-3 向量化一批文本，返回与输入顺序对齐的向量列表。"""
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": MODEL, "input": texts, "dimensions": DIMENSIONS},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"embeddings 接口返回 {resp.status_code}: {resp.text}")
    data = resp.json()["data"]
    # 官方建议按 data[].index 对齐输入下标，不要假设返回顺序
    ordered = sorted(data, key=lambda item: item["index"])
    return [item["embedding"] for item in ordered]


def cosine_similarity(vec_a, vec_b):
    """手写余弦相似度，不依赖 numpy。"""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    if not FAQ_PATH.exists():
        sys.exit(f"找不到 {FAQ_PATH}，请把 faq.txt 放在脚本同目录下")

    faqs = [line.strip() for line in FAQ_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not faqs:
        sys.exit("faq.txt 是空的")
    print(f"从 faq.txt 读到 {len(faqs)} 条 FAQ")

    # 建索引：分批向量化（embedding-3 单次最多 64 条）
    vectors = []
    for start in range(0, len(faqs), BATCH_SIZE):
        batch = faqs[start:start + BATCH_SIZE]
        vectors.extend(embed(batch, api_key))
        print(f"已向量化 {min(start + BATCH_SIZE, len(faqs))}/{len(faqs)}")

    index = {"model": MODEL, "dimensions": DIMENSIONS, "texts": faqs, "vectors": vectors}
    VECTORS_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"向量索引已写入 {VECTORS_PATH}")

    # 检索：从刚写好的 vectors.json 加载索引，再把查询语句向量化
    index = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    query_vector = embed([QUERY], api_key)[0]

    scored = [
        (cosine_similarity(query_vector, vec), text)
        for vec, text in zip(index["vectors"], index["texts"])
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    print(f"\n查询「{QUERY}」最相近的 {TOP_K} 条：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. {text}（相似度 {score:.4f}）")


if __name__ == "__main__":
    main()
