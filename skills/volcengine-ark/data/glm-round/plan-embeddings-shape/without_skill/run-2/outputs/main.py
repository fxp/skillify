"""火山方舟 Agent Plan 文本向量化示例。

使用 Agent Plan 专属 OpenAI 兼容端点调用内置的 doubao-embedding-vision
向量化模型，把三段文本转成向量，通过 dimensions 参数指定输出 1024 维，
最后打印并校验每条向量的实际维度。

运行前：
    export ARK_AGENT_PLAN_API_KEY="你的 Agent Plan 专属 API Key"
然后：
    python3 main.py
"""

import os
import sys

import requests

# Agent Plan 专属 Base URL（兼容 OpenAI 接口协议）。
# 注意：必须使用 Agent Plan 的专属 API Key，普通方舟 API Key 无法在此使用。
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"

# Agent Plan 内置向量化模型（对应 doubao-embedding-vision-251215，上下文 128k）
MODEL = "doubao-embedding-vision"

# 目标向量维度：doubao-embedding-vision-250615 及之后版本支持
# 通过 dimensions 参数降维输出，可取 1024 或 2048
DIMENSIONS = 1024

TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def get_embedding(text: str, api_key: str) -> list:
    """调用 Agent Plan 的 embeddings 接口，返回单条文本的向量。"""
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,
            "dimensions": DIMENSIONS,
            "encoding_format": "float",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        # 带上响应体便于排查：鉴权失败 / 额度不足 / 参数不合法等
        sys.exit(f"调用 embeddings 失败，HTTP {resp.status_code}：{resp.text}")
    return resp.json()["data"][0]["embedding"]


def main() -> None:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        sys.exit("请先设置环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 专属 API Key）")

    all_match = True
    for i, text in enumerate(TEXTS):
        vector = get_embedding(text, api_key)
        dim = len(vector)
        match = dim == DIMENSIONS
        all_match = all_match and match
        print(
            f"[{i}] 文本: {text} | 向量实际长度: {dim} | "
            f"预期: {DIMENSIONS} | {'OK' if match else 'MISMATCH'}"
        )

    if not all_match:
        sys.exit("存在向量维度与 1024 不符，请检查模型是否支持 dimensions 参数")
    print(f"全部 {len(TEXTS)} 条向量均为 {DIMENSIONS} 维，符合预期。")


if __name__ == "__main__":
    main()
