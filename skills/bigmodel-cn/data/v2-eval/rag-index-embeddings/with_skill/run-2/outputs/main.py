#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小可用的 FAQ 语义检索。

1. 用智谱 embedding-3 把 faq.txt 的每一行向量化，结果存到同目录的 vectors.json；
2. 用查询「发票怎么开」算余弦相似度，取 top-3，把最相近的三条原文打印到 stdout。

依赖：仅 requests（相似度用纯 Python 计算，不用 numpy）。
运行：python3 main.py（API Key 从环境变量 ZHIPUAI_API_KEY 读取）
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # embedding-3 支持自定义维度；索引与查询必须用同一 model+dimensions
BATCH_SIZE = 64  # 官方限制：embedding-3 的 input 数组单次最多 64 条
QUERY = "发票怎么开"
TOP_K = 3

FAQ_NAME = "faq.txt"
VEC_NAME = "vectors.json"


def find_faq_path():
    """在脚本目录、当前目录及其上级目录里找 faq.txt，谁先存在用谁。"""
    for root in (Path(__file__).resolve().parent, Path.cwd()):
        for cand in (root, *list(root.parents)[:4]):
            if (cand / FAQ_NAME).is_file():
                return cand / FAQ_NAME
    sys.exit(f"找不到 {FAQ_NAME}：已尝试脚本目录、当前目录及其上级目录")


def load_lines(faq_path):
    lines = [ln.strip() for ln in faq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        sys.exit(f"{faq_path} 里没有有效内容")
    return lines


def embed(texts, api_key):
    """调用 embeddings 接口，返回与 texts 顺序一致的向量列表。"""
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL, "input": texts, "dimensions": DIMENSIONS},
            timeout=60,
        )
    except requests.RequestException as exc:
        sys.exit(f"请求 embeddings 接口失败：{exc}")
    if resp.status_code != 200:
        sys.exit(f"embeddings 接口返回 HTTP {resp.status_code}：{resp.text}")
    data = resp.json().get("data")
    if not data or len(data) != len(texts):
        sys.exit(f"embeddings 响应条数异常（期望 {len(texts)}）：{resp.text}")
    # 官方建议按 data[].index 对齐结果，不要假设返回顺序与输入一致
    return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]


def build_index(lines, vec_path, api_key):
    """把每行 FAQ 向量化并写入 vectors.json；已有内容一致的缓存则直接复用。"""
    if vec_path.is_file():
        try:
            cached = json.loads(vec_path.read_text(encoding="utf-8"))
            if (
                cached.get("model") == MODEL
                and cached.get("dimensions") == DIMENSIONS
                and [it["text"] for it in cached["items"]] == lines
            ):
                print(f"复用已有向量缓存 {vec_path}（{len(lines)} 条）", file=sys.stderr)
                return [it["embedding"] for it in cached["items"]]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # 缓存损坏就重建

    vectors = []
    for start in range(0, len(lines), BATCH_SIZE):
        batch = lines[start : start + BATCH_SIZE]
        vectors.extend(embed(batch, api_key))
        print(f"已向量化 {min(start + BATCH_SIZE, len(lines))}/{len(lines)} 条", file=sys.stderr)

    vec_path.write_text(
        json.dumps(
            {
                "model": MODEL,
                "dimensions": DIMENSIONS,
                "items": [{"text": t, "embedding": v} for t, v in zip(lines, vectors)],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"向量已写入 {vec_path}", file=sys.stderr)
    return vectors


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

    faq_path = find_faq_path()
    lines = load_lines(faq_path)

    doc_vectors = build_index(lines, faq_path.parent / VEC_NAME, api_key)
    query_vec = embed([QUERY], api_key)[0]

    scored = sorted(
        ((cosine(query_vec, dv), text) for text, dv in zip(lines, doc_vectors)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    print(f"查询：{QUERY}")
    print(f"top-{TOP_K} 最相近：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. [{score:.4f}] {text}")


if __name__ == "__main__":
    main()
