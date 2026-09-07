"""最小可用的 FAQ 检索：embedding-3 向量化 + 纯 Python 余弦相似度取 top-3。

用法：
    export ZHIPUAI_API_KEY=你的Key
    python3 main.py

依赖：仅 requests（不用 numpy，余弦相似度手算）。
"""

import json
import math
import os
import sys
from pathlib import Path

import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
MODEL = "embedding-3"
QUERY = "发票怎么开"
BATCH_SIZE = 32  # 官方限制单次最多 64 条文本，留些余量

# faq.txt 和 vectors.json 都放在脚本同目录
BASE_DIR = Path(__file__).resolve().parent
FAQ_PATH = BASE_DIR / "faq.txt"
VECTORS_PATH = BASE_DIR / "vectors.json"


def get_embeddings(texts, api_key):
    """调用智谱 embedding-3，返回与 texts 顺序一一对应的向量列表。"""
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
            raise RuntimeError(
                "调用 embedding 接口失败（HTTP %s）：%s" % (resp.status_code, resp.text)
            )
        items = resp.json()["data"]
        # 接口按 index 标记每条向量对应哪条输入，按 index 排好序再收集，防止乱序
        items.sort(key=lambda item: item["index"])
        if len(items) != len(batch):
            raise RuntimeError("接口返回的向量数量与输入条数不一致")
        vectors.extend(item["embedding"] for item in items)
    return vectors


def cosine_similarity(a, b):
    """纯 Python 实现的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def main():
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        sys.exit("错误：请先设置环境变量 ZHIPUAI_API_KEY")

    if not FAQ_PATH.exists():
        sys.exit("错误：找不到 " + str(FAQ_PATH))

    # 每行一条 FAQ，去掉首尾空白，跳过空行
    faq_items = [
        line.strip()
        for line in FAQ_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not faq_items:
        sys.exit("错误：faq.txt 里没有内容")

    print("正在向量化 %d 条 FAQ……" % len(faq_items))
    faq_vectors = get_embeddings(faq_items, api_key)

    # 结果落盘成同目录的 vectors.json
    records = [
        {"text": text, "embedding": vec}
        for text, vec in zip(faq_items, faq_vectors)
    ]
    VECTORS_PATH.write_text(
        json.dumps(records, ensure_ascii=False),
        encoding="utf-8",
    )
    print("向量已写入 %s\n" % VECTORS_PATH)

    # 查询句单独向量化，再和每条 FAQ 算余弦相似度
    query_vector = get_embeddings([QUERY], api_key)[0]
    scored = sorted(
        (
            (cosine_similarity(query_vector, vec), text)
            for vec, text in zip(faq_vectors, faq_items)
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )

    print("查询：%s" % QUERY)
    for rank, (score, text) in enumerate(scored[:3], start=1):
        print("Top%d 相似度 %.4f：%s" % (rank, score, text))


if __name__ == "__main__":
    main()
