#!/usr/bin/env python3
"""最小 FAQ 语义检索示例。

流程：
1. 读取同目录 faq.txt（每行一条 FAQ），用智谱 embedding-3 批量向量化；
2. 向量连同原文存入同目录 vectors.json；
3. 用「发票怎么开」作为查询，手写余弦相似度（不用 numpy）取 top-3，
   把三条最相近的 FAQ 原文打印到 stdout。

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
BATCH_SIZE = 64  # embedding-3 的 input 数组单次最多 64 条
QUERY = "发票怎么开"
TOP_K = 3

BASE_DIR = Path(__file__).resolve().parent


def embed(texts, api_key):
    """调用 embedding-3 把一批文本转向量，返回与输入顺序对齐的向量列表。"""
    last_err = None
    for attempt in range(3):  # 网络抖动时简单重试
        if attempt:
            time.sleep(2 * attempt)
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": MODEL, "input": texts},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"embeddings 接口返回 {resp.status_code}: {resp.text}")
            data = resp.json()["data"]
        except (requests.RequestException, RuntimeError, KeyError, ValueError) as e:
            last_err = e
            continue
        # 官方文档：data[].index 对应输入数组下标，按 index 对齐，不假设返回顺序
        vectors = [None] * len(texts)
        for item in data:
            vectors[item["index"]] = item["embedding"]
        if any(v is None for v in vectors):
            raise RuntimeError("embeddings 返回的向量数量与输入不一致")
        return vectors
    raise RuntimeError(f"调用 embeddings 接口失败：{last_err}")


def cosine(a, b):
    """余弦相似度，纯 Python 实现。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    # faq.txt 优先取脚本同目录，其次当前工作目录
    faq_path = next(
        (p for p in (BASE_DIR / "faq.txt", Path("faq.txt")) if p.is_file()), None
    )
    if faq_path is None:
        sys.exit("错误：找不到 faq.txt，请把它放在脚本同目录或当前目录下")

    lines = [ln.strip() for ln in faq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        sys.exit("错误：faq.txt 是空的")
    print(f"从 {faq_path} 读取 {len(lines)} 条 FAQ，开始向量化……")

    vectors = []
    for start in range(0, len(lines), BATCH_SIZE):
        batch = lines[start:start + BATCH_SIZE]
        vectors.extend(embed(batch, api_key))
        print(f"  已向量化 {min(start + BATCH_SIZE, len(lines))}/{len(lines)} 条")

    # 向量连同原文落盘，检索阶段再从文件读回
    vectors_path = faq_path.parent / "vectors.json"
    with open(vectors_path, "w", encoding="utf-8") as f:
        json.dump(
            {"model": MODEL, "source": faq_path.name, "items": [
                {"text": t, "embedding": v} for t, v in zip(lines, vectors)
            ]},
            f,
            ensure_ascii=False,
        )
    print(f"向量已写入 {vectors_path}")

    with open(vectors_path, encoding="utf-8") as f:
        items = json.load(f)["items"]

    query_vec = embed([QUERY], api_key)[0]
    scored = sorted(
        ((cosine(query_vec, it["embedding"]), it["text"]) for it in items),
        key=lambda x: x[0],
        reverse=True,
    )[:TOP_K]

    print(f"\n查询：{QUERY}")
    print(f"最相近的 Top {TOP_K} 条 FAQ：")
    for rank, (score, text) in enumerate(scored, 1):
        print(f"{rank}. [{score:.4f}] {text}")


if __name__ == "__main__":
    main()
