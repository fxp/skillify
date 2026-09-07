# -*- coding: utf-8 -*-
"""火山方舟 Agent Plan · 文本向量化（Embedding）示例

调用 Agent Plan 订阅的向量化接口，把三段中文文本转成 1024 维向量，
并打印每条向量的实际长度（len(embedding)）以确认维度。

接口要点（OpenAI 兼容）：
    POST https://ark.cn-beijing.volces.com/api/plan/v3/embeddings
    - Agent Plan 专属 Base URL 是 /api/plan/v3（与按量付费的 /api/v3 不同）
    - 模型 doubao-embedding-vision 默认输出 2048 维，
      通过请求体中的 dimension 参数降维到 1024
    - 鉴权：Authorization: Bearer <ARK_AGENT_PLAN_API_KEY>

运行前：
    export ARK_AGENT_PLAN_API_KEY="你的 Agent Plan API Key"
    python3 main.py
"""

import os
import sys

import requests

# Agent Plan 订阅专属 Base URL
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = BASE_URL + "/embeddings"

MODEL = "doubao-embedding-vision"
DIMENSION = 1024  # 目标向量维度（该模型默认 2048，支持 1024 降维）
TIMEOUT = 60  # 秒

TEXTS = [
    "今天天气很好",
    "这部电影非常精彩",
    "服务器响应超时了",
]


def get_embedding(text, api_key):
    """调用 Agent Plan embeddings 接口，返回单条文本的向量（list[float]）。"""
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,  # 单条文本；该接口也支持字符串数组批量向量化
            "dimension": DIMENSION,  # 关键：请求 1024 维输出
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        # 带上响应体，方便排查 Key 无效 / 无权限 / 参数不合法等问题
        raise RuntimeError("HTTP %d: %s" % (resp.status_code, resp.text))
    return resp.json()["data"][0]["embedding"]


def main():
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print("错误：未设置环境变量 ARK_AGENT_PLAN_API_KEY，请先 export 后重试。",
              file=sys.stderr)
        sys.exit(1)

    print("模型: %s | 请求维度: %d" % (MODEL, DIMENSION))
    print("-" * 40)

    lengths = []
    try:
        for i, text in enumerate(TEXTS, 1):
            embedding = get_embedding(text, api_key)
            lengths.append(len(embedding))
            print("[%d] %s" % (i, text))
            print("    实际向量长度 = %d" % len(embedding))
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        print("请求失败: %s" % exc, file=sys.stderr)
        sys.exit(1)

    print("-" * 40)
    if lengths and all(n == DIMENSION for n in lengths):
        print("确认：%d 条向量全部为 %d 维" % (len(lengths), DIMENSION))
    else:
        print("注意：实际维度与请求的 %d 不一致 -> %s" % (DIMENSION, lengths))
        sys.exit(2)


if __name__ == "__main__":
    main()
