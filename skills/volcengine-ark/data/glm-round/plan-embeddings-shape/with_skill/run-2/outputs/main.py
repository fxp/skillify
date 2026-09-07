"""火山方舟 Agent Plan 文本向量化：三段文本 -> 1024 维向量，并打印实际维度。

接入要点（Agent Plan 专属，勿与标准 /api/v3 入口混用）：
- Base URL: https://ark.cn-beijing.volces.com/api/plan/v3（Agent Plan 专属 Key 打 /api/v3 会 401）
- 鉴权: Authorization: Bearer $ARK_AGENT_PLAN_API_KEY（Agent Plan 控制台的专属 Key）
- 模型: doubao-embedding-vision（Plan 入口用不带日期的 Model Name）
- 维度: dimensions 只接受 1024 / 2048，默认 2048，必须显式传 1024

运行: python3 main.py（仅依赖 requests）
"""

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBED_URL = f"{BASE_URL}/embeddings"
MODEL = "doubao-embedding-vision"
DIMENSIONS = 1024
TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def embed_texts(texts, headers):
    """向量化一批文本，返回与 texts 顺序一致的向量列表。

    优先一次请求传入字符串数组（OpenAI embeddings 标准形态）；
    若服务端不接受数组或未按输入条数返回，回退为逐条请求（单字符串输入是
    Agent Plan 入口实测可用的形态）。
    """
    try:
        resp = requests.post(
            EMBED_URL,
            headers=headers,
            json={"model": MODEL, "input": texts, "dimensions": DIMENSIONS},
            timeout=60,
        )
        resp.raise_for_status()
        by_index = {item["index"]: item["embedding"] for item in resp.json()["data"]}
        if len(by_index) == len(texts):
            return [by_index[i] for i in range(len(texts))]
    except (requests.RequestException, KeyError, ValueError):
        pass  # 回退到逐条请求；系统性错误（如 401）会在下方复现并抛出

    vectors = []
    for text in texts:
        resp = requests.post(
            EMBED_URL,
            headers=headers,
            json={"model": MODEL, "input": text, "dimensions": DIMENSIONS},
            timeout=60,
        )
        resp.raise_for_status()
        vectors.append(resp.json()["data"][0]["embedding"])
    return vectors


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 专属 Key，与方舟 API Key 不通用）")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    vectors = embed_texts(TEXTS, headers)

    for i, (text, vec) in enumerate(zip(TEXTS, vectors), 1):
        print(f"[{i}] {text} -> 向量实际长度: {len(vec)}")
    ok = all(len(v) == DIMENSIONS for v in vectors)
    print(f"确认: {len(vectors)} 条向量实际长度均为 {DIMENSIONS} -> {'通过' if ok else '不通过'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
