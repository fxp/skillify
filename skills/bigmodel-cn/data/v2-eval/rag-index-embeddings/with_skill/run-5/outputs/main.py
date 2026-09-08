#!/usr/bin/env python3
"""用智谱 embedding-3 给 faq.txt 建一个最小向量索引，并做余弦相似度 top-3 检索。

用法：
    export ZHIPUAI_API_KEY=<你的 Key>
    python3 main.py

流程：
    1. 读取同目录 faq.txt（每行一条 FAQ）；
    2. 调用 POST /paas/v4/embeddings（model=embedding-3，dimensions=1024）批量向量化，
       结果连同原文写入同目录 vectors.json；已存在且内容未变则直接复用，不重复调 API；
    3. 把查询「发票怎么开」向量化（与建索引使用同一 model + dimensions 组合）；
    4. 纯 Python 计算余弦相似度，打印最相近的 top-3 原文。

依赖：仅 requests（向量运算手写，不用 numpy）。
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
DIMENSIONS = 1024  # embedding-3 支持 256/512/1024/2048；索引与查询必须用同一组合
BATCH_SIZE = 64    # embedding-3 单次请求 input 数组最多 64 条，超出需分批
QUERY = "发票怎么开"
TOP_K = 3


def load_faq():
    """优先读脚本同目录的 faq.txt，找不到再退回当前工作目录。"""
    for base in (Path(__file__).resolve().parent, Path.cwd()):
        path = base / "faq.txt"
        if path.is_file():
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            return path, lines
    sys.exit("错误：找不到 faq.txt（已尝试脚本所在目录和当前目录）")


def embed_texts(texts, api_key):
    """把一批文本（可能超过 64 条）向量化，返回与输入等长的向量列表。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        resp = requests.post(
            API_URL,
            headers=headers,
            json={"model": MODEL, "input": batch, "dimensions": DIMENSIONS},
            timeout=60,
        )
        if resp.status_code != 200:
            sys.exit(f"错误：embeddings 接口返回 HTTP {resp.status_code}：{resp.text}")
        data = resp.json()["data"]
        if len(data) != len(batch):
            sys.exit("错误：接口返回的向量条数与输入不一致")
        # 官方建议按 index 对齐，不要假设返回顺序与输入一致
        aligned = [None] * len(batch)
        for item in data:
            aligned[item["index"]] = item["embedding"]
        if any(v is None for v in aligned):
            sys.exit("错误：接口返回的向量 index 不连续")
        vectors.extend(aligned)
    return vectors


def cosine_similarity(a, b):
    if len(a) != len(b):
        sys.exit(f"错误：向量维度不一致（{len(a)} vs {len(b)}），请重建 vectors.json")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_or_load_index(lines, vectors_path, api_key):
    """vectors.json 存在且与当前 FAQ 内容一致时复用，否则重建。"""
    if vectors_path.is_file():
        try:
            cached = json.loads(vectors_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached = None
        if (
            cached
            and cached.get("model") == MODEL
            and cached.get("dimensions") == DIMENSIONS
            and [item["text"] for item in cached["items"]] == lines
        ):
            print(f"从 {vectors_path.name} 加载 {len(lines)} 条缓存向量，跳过重新向量化")
            return [item["embedding"] for item in cached["items"]]

    print(f"正在向量化 {len(lines)} 条 FAQ（{MODEL}，{DIMENSIONS} 维，每批 {BATCH_SIZE} 条）……")
    vectors = embed_texts(lines, api_key)
    payload = {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "items": [{"text": t, "embedding": v} for t, v in zip(lines, vectors)],
    }
    vectors_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"向量已写入 {vectors_path}")
    return vectors


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    faq_path, lines = load_faq()
    if not lines:
        sys.exit("错误：faq.txt 是空的")
    vectors_path = faq_path.parent / "vectors.json"

    index = build_or_load_index(lines, vectors_path, api_key)

    query_vec = embed_texts([QUERY], api_key)[0]
    scored = sorted(
        ((cosine_similarity(query_vec, vec), text) for vec, text in zip(index, lines)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    print(f"\n查询：{QUERY}")
    print(f"最相近的 top-{TOP_K}：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. [{score:.4f}] {text}")


if __name__ == "__main__":
    main()
