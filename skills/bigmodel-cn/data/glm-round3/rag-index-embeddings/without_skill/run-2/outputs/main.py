# -*- coding: utf-8 -*-
"""最小可用的 FAQ 检索：智谱 embedding-3 + 余弦相似度 top-3。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

依赖：仅 requests（不用 numpy）。faq.txt 与本脚本同目录，每行一条 FAQ；
向量结果写入同目录 vectors.json；查询「发票怎么开」打印最相近的 3 条原文。
"""

import json
import math
import os
import sys

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
QUERY = "发票怎么开"
TOP_K = 3
BATCH_SIZE = 64  # embedding-3 的 input 数组单次最多 64 条


def load_faqs(base_dir):
    """读取 faq.txt，返回非空行列表。"""
    candidates = [
        os.path.join(base_dir, "faq.txt"),
        os.path.join(os.path.dirname(base_dir), "faq.txt"),
    ]
    faq_path = next((p for p in candidates if os.path.isfile(p)), None)
    if faq_path is None:
        sys.exit("找不到 faq.txt，请把它和 main.py 放在同一个目录下")
    with open(faq_path, "r", encoding="utf-8") as f:
        faqs = [line.strip() for line in f if line.strip()]
    if not faqs:
        sys.exit("faq.txt 是空的")
    return faq_path, faqs


def embed(texts, api_key):
    """调用 embedding-3，按输入顺序返回每条文本的向量（list[list[float]]）。"""
    headers = {
        "Authorization": "Bearer " + api_key,
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
            # 智谱出错时 body 是 {"error": {"code":..., "message":...}}
            message = resp.text
            try:
                message = resp.json()["error"]["message"]
            except Exception:
                pass
            sys.exit("embedding 接口请求失败 HTTP %s: %s" % (resp.status_code, message))
        data = resp.json()["data"]
        data.sort(key=lambda item: item["index"])  # 保证与输入顺序一致
        vectors.extend(item["embedding"] for item in data)
    return vectors


def cosine(a, b):
    """手写余弦相似度，不依赖 numpy。"""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("请先设置环境变量 ZHIPUAI_API_KEY")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    faq_path, faqs = load_faqs(base_dir)
    print("读取 %s，共 %d 条 FAQ" % (faq_path, len(faqs)))

    # 1. 全量向量化并落盘
    vectors = embed(faqs, api_key)
    vectors_path = os.path.join(os.path.dirname(faq_path), "vectors.json")
    with open(vectors_path, "w", encoding="utf-8") as f:
        json.dump(
            {"model": MODEL, "dim": len(vectors[0]), "faqs": faqs, "vectors": vectors},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("向量已写入 %s" % vectors_path)

    # 2. 查询向量化 + 余弦相似度 top-3
    query_vec = embed([QUERY], api_key)[0]
    scored = [
        (i, cosine(query_vec, vec))
        for i, vec in enumerate(vectors)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    print("查询：%s" % QUERY)
    print("最相近的 %d 条：" % TOP_K)
    for rank, (i, score) in enumerate(scored[:TOP_K], 1):
        print("%d. %s（相似度 %.4f）" % (rank, faqs[i], score))


if __name__ == "__main__":
    main()
