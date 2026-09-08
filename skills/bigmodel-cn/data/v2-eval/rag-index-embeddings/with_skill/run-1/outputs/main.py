#!/usr/bin/env python3
"""最小可用的 FAQ 检索：用智谱 embedding-3 给 faq.txt 每行建向量索引，
存成同目录 vectors.json，再用「发票怎么开」做查询，按余弦相似度取 top-3。

运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 512  # embedding-3 支持 256/512/1024/2048；建库和查询必须用同一组合
BATCH_SIZE = 64   # embedding-3 单次请求 input 数组上限 64 条，超过要分批
QUERY = "发票怎么开"
TOP_K = 3


def find_faq_path() -> Path:
    """按 脚本目录 → 当前目录 → 各自的上级目录 顺序查找 faq.txt。"""
    here = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates = [here / "faq.txt", cwd / "faq.txt"]
    for base in (cwd, here):
        candidates.extend(parent / "faq.txt" for parent in list(base.parents)[:4])
    for path in candidates:
        if path.is_file():
            return path
    sys.exit("找不到 faq.txt：请把它放在脚本同目录（或运行目录及其上级）下。")


def embed(texts, api_key):
    """调用 embedding-3，返回与 texts 顺序对齐的向量列表。

    分批发送；响应里 data[*].index 是批内下标，按它回填而非假设返回顺序。
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    vectors = [None] * len(texts)
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            API_URL,
            headers=headers,
            json={"model": MODEL, "input": batch, "dimensions": DIMENSIONS},
            timeout=60,
        )
        if resp.status_code != 200:  # 智谱的错误详情在响应体里，带出来便于排查
            sys.exit(f"embeddings 调用失败 HTTP {resp.status_code}: {resp.text}")
        for item in resp.json()["data"]:
            vectors[start + item["index"]] = item["embedding"]
    if any(v is None for v in vectors):
        sys.exit("embeddings 返回结果不完整，有输入没拿到向量")
    return vectors


def cosine(a, b):
    """纯 Python 余弦相似度（不用 numpy）。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    faq_path = find_faq_path()
    lines = [ln.strip() for ln in faq_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]  # 跳过空行
    if not lines:
        sys.exit("faq.txt 里没有内容")

    print(f"正在向量化 {len(lines)} 条 FAQ（{MODEL}, {DIMENSIONS} 维）……")
    vectors = embed(lines, api_key)

    vectors_path = faq_path.parent / "vectors.json"
    vectors_path.write_text(
        json.dumps(
            {"model": MODEL, "dimensions": DIMENSIONS, "texts": lines, "vectors": vectors},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"向量已写入 {vectors_path}")

    query_vec = embed([QUERY], api_key)[0]
    scored = sorted(
        ((cosine(query_vec, vec), text) for text, vec in zip(lines, vectors)),
        key=lambda pair: pair[0],
        reverse=True,
    )[:TOP_K]

    print(f"\n查询：{QUERY}")
    print(f"最相近的 {TOP_K} 条：")
    for rank, (score, text) in enumerate(scored, 1):
        print(f"{rank}. [{score:.4f}] {text}")


if __name__ == "__main__":
    main()
