"""用火山方舟 Agent Plan 对三段文本做向量化，并打印每条向量的实际长度。

Agent Plan 专属三件套（与标准 /api/v3、Coding Plan /api/coding/v3 互不通用，混用会 401）：
  - Base URL: https://ark.cn-beijing.volces.com/api/plan/v3
  - API Key:  环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 专属 Key，不是方舟 API Key）
  - Model:    doubao-embedding-vision（Plan 入口用 Model Name，响应里回显 doubao-embedding-vision-251215）

embeddings 接口要点（Agent Plan 入口 2026-09-04 实测）：
  - POST /embeddings 为 OpenAI 形态，input 只收字符串（传多模态对象数组会 400 "expected a string"），
    因此对多条文本逐条请求，取 data[0]["embedding"]；
  - 不传 dimensions 默认 2048 维，只支持 1024 / 2048，本脚本显式传 1024。
"""

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"
MODEL = "doubao-embedding-vision"
DIMENSIONS = 1024
TIMEOUT = 60

TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def embed_text(text: str, api_key: str) -> list:
    """对单条文本调用向量化接口，返回 embedding 浮点列表。"""
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,             # 字符串，不是数组
            "dimensions": DIMENSIONS,  # 不传默认 2048 维
        },
        timeout=TIMEOUT,
    )
    if not resp.ok:
        # 常见错误：401 = Key/入口不匹配（Plan Key 误打 /api/v3 也会 401）；
        #          404 UnsupportedModel = model 名写错（Plan 入口要用 Model Name）
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    data = resp.json()["data"]  # OpenAI 形态：data 是数组
    return data[0]["embedding"]


def main() -> None:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        sys.exit("缺少环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 专属 API Key）")

    lengths = []
    for i, text in enumerate(TEXTS):
        vec = embed_text(text, api_key)
        lengths.append(len(vec))
        print(f"[{i}] {text} -> 向量实际长度: {len(vec)}")

    ok = all(n == DIMENSIONS for n in lengths)
    print(f"期望维度: {DIMENSIONS}，实际: {lengths}，{'全部一致 ✓' if ok else '存在不一致 ✗'}")


if __name__ == "__main__":
    main()
