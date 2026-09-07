#!/usr/bin/env python3
"""最小可用的 FAQ 检索脚本。

流程：
1. 读取脚本同目录下的 faq.txt（每行一条 FAQ）；
2. 调用智谱 embedding-3 把每行向量化，结果存到同目录的 vectors.json；
3. 用「发票怎么开」做查询，算余弦相似度，打印最相近的 top-3 原文。

依赖：仅 requests（余弦相似度用纯 Python 计算，不用 numpy）。
运行：ZHIPUAI_API_KEY=xxx python3 main.py
"""

import json
import math
import os
import time
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
QUERY = "发票怎么开"
TOP_K = 3
BATCH_SIZE = 64  # 官方限制：单次请求 input 数组最多 64 条
RETRIES = 3

# 以脚本自身所在目录为基准，保证在任何工作目录下执行都能找到 faq.txt
BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def embed_texts(texts, api_key):
    """调用 embedding-3 接口，返回与 texts 顺序一致的向量列表。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        body = _post_with_retry({"model": MODEL, "input": batch}, headers)
        data = body.get("data")
        if not data or len(data) != len(batch):
            raise SystemExit(f"接口返回异常: {json.dumps(body, ensure_ascii=False)}")
        # 按 index 排序，确保向量与输入文本顺序一一对应
        for item in sorted(data, key=lambda d: d.get("index", 0)):
            vectors.append(item["embedding"])
    return vectors


def _post_with_retry(payload, headers):
    last_exc = None
    for attempt in range(RETRIES):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < RETRIES - 1:
                time.sleep(1 + attempt)
    raise SystemExit(f"调用 embedding 接口失败: {last_exc}")


def cosine_similarity(a, b):
    """纯 Python 余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_faqs():
    if not FAQ_PATH.exists():
        raise SystemExit(f"找不到 {FAQ_PATH}")
    lines = FAQ_PATH.read_text(encoding="utf-8-sig").splitlines()
    faqs = [line.strip() for line in lines if line.strip()]
    if not faqs:
        raise SystemExit("faq.txt 中没有有效内容")
    return faqs


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量 ZHIPUAI_API_KEY")

    faqs = load_faqs()
    print(f"读取到 {len(faqs)} 条 FAQ，开始向量化……")

    embeddings = embed_texts(faqs, api_key)
    VECTORS_PATH.write_text(
        json.dumps(
            {"model": MODEL, "count": len(faqs), "lines": faqs, "embeddings": embeddings},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"向量已保存到 {VECTORS_PATH}")

    query_vec = embed_texts([QUERY], api_key)[0]
    scored = sorted(
        ((cosine_similarity(query_vec, vec), text) for text, vec in zip(faqs, embeddings)),
        key=lambda pair: pair[0],
        reverse=True,
    )

    print(f"\n查询：{QUERY}")
    print(f"最相近的 {TOP_K} 条：")
    for rank, (score, text) in enumerate(scored[:TOP_K], 1):
        print(f"{rank}. {text}（相似度 {score:.4f}）")


if __name__ == "__main__":
    main()
