"""最小可用的 FAQ 向量检索。

流程：读同目录 faq.txt -> 用智谱 embedding-3 逐批向量化 -> 存 vectors.json
-> 用查询「发票怎么开」算余弦相似度，打印 top-3 原文。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
仅依赖 requests，余弦相似度用纯 Python 计算。
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

EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # 索引与查询必须用同一 model + dimensions，否则向量空间不一致
BATCH_SIZE = 64    # embedding-3 单次请求 input 数组最多 64 条
QUERY = "发票怎么开"
TOP_K = 3


def embed(texts, api_key):
    """调用 embedding-3，返回与输入顺序对齐的向量列表。"""
    resp = requests.post(
        EMBEDDING_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": MODEL, "input": texts, "dimensions": DIMENSIONS},
        timeout=60,
    )
    if not resp.ok:
        sys.exit(f"embeddings 调用失败 HTTP {resp.status_code}: {resp.text}")
    data = resp.json().get("data") or []
    if len(data) != len(texts):
        sys.exit(f"embeddings 返回条数 {len(data)} 与输入 {len(texts)} 不符: {resp.text}")
    # 官方建议按 index 对齐结果，不要假设返回顺序
    return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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

    vectors = []
    for start in range(0, len(faqs), BATCH_SIZE):
        batch = faqs[start:start + BATCH_SIZE]
        vectors.extend(embed(batch, api_key))
        print(f"已向量化 {min(start + BATCH_SIZE, len(faqs))}/{len(faqs)} 条")

    VECTORS_PATH.write_text(
        json.dumps(
            {"model": MODEL, "dimensions": DIMENSIONS, "texts": faqs, "vectors": vectors},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"向量已写入 {VECTORS_PATH}")

    query_vec = embed([QUERY], api_key)[0]
    scored = sorted(
        ((cosine(query_vec, vec), text) for vec, text in zip(vectors, faqs)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    print(f"\n查询：{QUERY}")
    print(f"最相近的 top-{TOP_K}：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. {text}（相似度 {score:.4f}）")


if __name__ == "__main__":
    main()
