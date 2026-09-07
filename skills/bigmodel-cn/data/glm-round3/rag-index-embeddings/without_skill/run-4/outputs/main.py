# -*- coding: utf-8 -*-
"""最小 FAQ 向量检索：智谱 embedding-3 + 余弦相似度 top-3。

流程：
1. 逐行读取同目录 faq.txt（一行一条 FAQ）；
2. 调用 embedding-3 批量向量化（官方限制：单次请求 input 数组最多 64 条），
   结果存为同目录 vectors.json；
3. 用「发票怎么开」做查询，再调一次 embedding-3 拿查询向量，
   与全部 FAQ 向量算余弦相似度，把最相近的 top-3 原文打印到 stdout。

只依赖 requests 和标准库（相似度纯手算），API Key 从环境变量
ZHIPUAI_API_KEY 读取。直接 `python3 main.py` 运行。
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

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
BATCH_SIZE = 64  # embedding-3 单次请求 input 数组最多 64 条
TIMEOUT = 60
QUERY = "发票怎么开"
TOP_K = 3


def embed(texts):
    """调用 embedding-3 向量化 texts，返回与输入顺序一致的向量列表。"""
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：未设置环境变量 ZHIPUAI_API_KEY")

    headers = {"Authorization": "Bearer " + api_key}
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            API_URL,
            headers=headers,
            json={"model": MODEL, "input": batch},
            timeout=TIMEOUT,
        )
        try:
            body = resp.json()
        except ValueError:
            sys.exit("错误：embedding 接口返回了非 JSON 内容：%s" % resp.text)
        if resp.status_code != 200 or body.get("error") or not body.get("data"):
            sys.exit(
                "错误：embedding 接口调用失败（HTTP %s）：%s"
                % (resp.status_code, body.get("error") or resp.text)
            )
        # 按 index 归位，保证向量顺序与输入文本一一对应
        batch_vectors = [None] * len(batch)
        for item in body["data"]:
            batch_vectors[item["index"]] = item["embedding"]
        if any(v is None for v in batch_vectors):
            sys.exit("错误：接口返回的向量数量与输入不一致")
        vectors.extend(batch_vectors)
    return vectors


def cosine_similarity(vec_a, vec_b):
    """纯 Python 计算两个向量的余弦相似度。"""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def load_faqs():
    if not FAQ_PATH.exists():
        sys.exit("错误：找不到 %s" % FAQ_PATH)
    faqs = [
        line.strip()
        for line in FAQ_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not faqs:
        sys.exit("错误：faq.txt 中没有内容")
    return faqs


def main():
    faqs = load_faqs()
    print("读取到 %d 条 FAQ，开始调用 embedding-3 向量化……" % len(faqs))

    vectors = embed(faqs)
    with VECTORS_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {"model": MODEL, "texts": faqs, "vectors": vectors},
            f,
            ensure_ascii=False,
        )
    print("向量已写入 %s" % VECTORS_PATH)

    query_vector = embed([QUERY])[0]
    scored = sorted(
        ((cosine_similarity(query_vector, vec), text) for vec, text in zip(vectors, faqs)),
        key=lambda item: item[0],
        reverse=True,
    )
    print("与「%s」最相近的 top-%d：" % (QUERY, TOP_K))
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print("%d. %.4f %s" % (rank, score, text))


if __name__ == "__main__":
    main()
