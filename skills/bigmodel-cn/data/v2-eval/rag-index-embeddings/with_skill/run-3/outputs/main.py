#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小可用 FAQ 语义检索。

用智谱 embedding-3 把 faq.txt 的每一行向量化，存为同目录 vectors.json，
再对查询「发票怎么开」计算余弦相似度，打印 top-3 原文。

依赖：仅 requests（相似度用纯 Python 计算，不用 numpy）。
运行：ZHIPUAI_API_KEY=xxx python3 main.py
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
BATCH_SIZE = 64  # embedding-3 的 input 数组单批最多 64 条
QUERY = "发票怎么开"
TOP_K = 3

SCRIPT_DIR = Path(__file__).resolve().parent


def log(msg):
    print(msg, file=sys.stderr)


def find_faq_path():
    """faq.txt 优先取脚本同目录，其次当前工作目录。"""
    for candidate in (SCRIPT_DIR / "faq.txt", Path.cwd() / "faq.txt"):
        if candidate.is_file():
            return candidate
    sys.exit("错误：找不到 faq.txt（已尝试脚本目录和当前目录）")


def read_faq_lines(path):
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    faqs = [line for line in lines if line]  # 跳过空行
    if not faqs:
        sys.exit(f"错误：{path} 中没有有效内容")
    return faqs


def embed_texts(texts, api_key):
    """把 texts 向量化，按 64 条一批请求，返回与输入顺序一致的向量列表。"""
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        data = _request_embeddings(batch, api_key)
        # 官方建议按 data[].index 对齐，不要假设返回顺序
        by_index = {item["index"]: item["embedding"] for item in data}
        if len(by_index) != len(batch) or set(by_index) != set(range(len(batch))):
            raise RuntimeError("embeddings 返回的 index 与输入批次不匹配")
        vectors.extend(by_index[i] for i in range(len(batch)))
        log(f"已向量化 {min(start + BATCH_SIZE, len(texts))}/{len(texts)} 条")
    return vectors


def _request_embeddings(batch, api_key, attempts=3):
    payload = {"model": MODEL, "input": batch}
    headers = {"Authorization": f"Bearer {api_key}"}
    for attempt in range(attempts):
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            body = resp.json()
            if "error" in body:  # 部分错误以 200 + error 对象返回
                raise RuntimeError(f"embeddings 调用失败: {body['error']}")
            return body["data"]
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            time.sleep(2 ** attempt)  # 限流/瞬时故障，退避后重试
            continue
        try:
            message = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            message = resp.text
        raise RuntimeError(f"embeddings 请求失败 HTTP {resp.status_code}: {message}")
    raise RuntimeError("embeddings 请求重试次数已用尽")


def cosine_similarity(a, b):
    dot = norm_a = norm_b = 0.0
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
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    faq_path = find_faq_path()
    faqs = read_faq_lines(faq_path)
    log(f"从 {faq_path} 读到 {len(faqs)} 条 FAQ")

    # 1. 建索引：全部行向量化，存 vectors.json（与 faq.txt 同目录）
    vectors = embed_texts(faqs, api_key)
    vectors_path = faq_path.parent / "vectors.json"
    index = {
        "model": MODEL,
        "dimensions": len(vectors[0]),
        "count": len(faqs),
        "items": [
            {"text": text, "embedding": vector}
            for text, vector in zip(faqs, vectors)
        ],
    }
    vectors_path.write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8"
    )
    log(f"向量已写入 {vectors_path}")

    # 2. 检索：查询语句用同一 model 向量化（保证向量空间一致）
    query_vector = embed_texts([QUERY], api_key)[0]

    # 3. 纯 Python 余弦相似度，取 top-3
    scored = [
        (cosine_similarity(query_vector, vector), text)
        for text, vector in zip(faqs, vectors)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    print(f"查询：{QUERY}")
    print(f"最相近的 Top-{TOP_K}：")
    for rank, (score, text) in enumerate(scored[:TOP_K], start=1):
        print(f"{rank}. {text}（相似度 {score:.4f}）")


if __name__ == "__main__":
    main()
