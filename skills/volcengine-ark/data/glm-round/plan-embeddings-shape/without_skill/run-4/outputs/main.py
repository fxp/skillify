"""火山方舟 Agent Plan 文本向量化示例。

使用 Agent Plan 专属的 OpenAI 兼容端点（Base URL: https://ark.cn-beijing.volces.com/api/plan/v3）
把三段文本向量化为 1024 维向量，并打印每条向量的实际长度进行确认。

运行前：
    export ARK_AGENT_PLAN_API_KEY="你的 Agent Plan API Key"

运行：
    python3 main.py
"""

import os
import sys

import requests

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

# Agent Plan 专属 Base URL（区别于按量付费的 /api/v3）
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"

# Agent Plan 支持的向量化模型：doubao-embedding-vision 系列，
# 最高 2048 维，官方说明支持降维到 1024 使用（也可换成 doubao-embedding-vision-250615）
MODEL = os.environ.get("ARK_EMBEDDING_MODEL", "doubao-embedding-vision-251215")

DIMENSIONS = 1024  # 目标向量维度

TEXTS = [
    "今天天气很好",
    "这部电影非常精彩",
    "服务器响应超时了",
]


def get_embedding(text: str, api_key: str) -> list:
    """调用 Agent Plan 的 embeddings 接口，返回单条文本的向量。

    该向量化模型单次请求仅支持一段文本，因此逐条调用。
    """
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,
            "encoding_format": "float",  # 返回 float 数组，便于直接取长度
            "dimensions": DIMENSIONS,    # 降维到 1024
        },
        timeout=60,
    )
    resp.raise_for_status()

    data = resp.json()["data"]
    # 兼容两种返回格式：data 为列表（OpenAI 风格）或单个对象（multimodal 风格）
    item = data[0] if isinstance(data, list) else data
    return item["embedding"]


def main() -> None:
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"错误：未设置环境变量 {API_KEY_ENV}，请先 export 你的 Agent Plan API Key。", file=sys.stderr)
        sys.exit(1)

    print(f"模型：{MODEL}，目标维度：{DIMENSIONS}\n")

    for i, text in enumerate(TEXTS, 1):
        try:
            embedding = get_embedding(text, api_key)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:300] if exc.response is not None else ""
            print(f"[{i}/{len(TEXTS)}] 文本：{text!r} 调用失败：HTTP {status} {body}", file=sys.stderr)
            sys.exit(1)
        except requests.RequestException as exc:
            print(f"[{i}/{len(TEXTS)}] 文本：{text!r} 请求异常：{exc}", file=sys.stderr)
            sys.exit(1)

        dim = len(embedding)
        ok = "符合预期" if dim == DIMENSIONS else f"与预期的 {DIMENSIONS} 不符！"
        print(f"[{i}/{len(TEXTS)}] 文本：{text}")
        print(f"       向量长度：{dim}（{ok}），前 3 个分量：{embedding[:3]}")

    print("\n完成：三段文本均已向量化。")


if __name__ == "__main__":
    main()
