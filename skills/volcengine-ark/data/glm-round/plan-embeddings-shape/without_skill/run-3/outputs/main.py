# -*- coding: utf-8 -*-
"""
使用火山方舟 Agent Plan 的 Embeddings API 对文本做向量化,
通过 dimensions 参数把向量维度固定为 1024,最后校验每条向量的实际长度。

运行前提:
    1. pip install requests
    2. export ARK_AGENT_PLAN_API_KEY="你的 Agent Plan API Key"

直接运行: python3 main.py
"""

import json
import os
import sys

import requests

# 火山方舟 Agent Plan 专属 Base URL(注意与标准方舟 API 的 /api/v3 不同)
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = ARK_BASE_URL + "/embeddings"

# Agent Plan 支持的文本向量化模型(默认 2048 维,支持 512 / 1024 降维)
MODEL = "doubao-embedding-text-240515"

# 目标向量维度
DIMENSIONS = 1024

# 待向量化的文本
TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def get_api_key():
    """从环境变量读取 Agent Plan API Key。"""
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        print("错误: 请先设置环境变量 ARK_AGENT_PLAN_API_KEY,例如:")
        print('  export ARK_AGENT_PLAN_API_KEY="你的-API-Key"')
        sys.exit(1)
    return api_key


def embed_texts(api_key, texts):
    """调用 Embeddings API,返回按输入顺序排列的向量列表。"""
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": "Bearer {}".format(api_key),
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": texts,
            "encoding_format": "float",  # 返回 float 数组,便于直接统计长度
            "dimensions": DIMENSIONS,    # 指定向量维度为 1024
        },
        timeout=60,
    )
    if resp.status_code != 200:
        # 带上服务端返回的错误信息,方便排查(Key 无效、模型未开通等)
        raise RuntimeError(
            "Embeddings API 调用失败: HTTP {} {}".format(
                resp.status_code, resp.text
            )
        )

    # 响应 data 各项带 index 字段,按 index 归位保证与输入顺序一致
    vectors = [None] * len(texts)
    for item in resp.json().get("data", []):
        vectors[item["index"]] = item["embedding"]
    if any(v is None for v in vectors):
        raise RuntimeError(
            "Embeddings API 返回的向量数量与输入不一致: {}".format(
                json.dumps(resp.json(), ensure_ascii=False)[:500]
            )
        )
    return vectors


def main():
    api_key = get_api_key()
    print("模型: {}".format(MODEL))
    print("目标维度: {}".format(DIMENSIONS))
    print("-" * 40)

    vectors = embed_texts(api_key, TEXTS)

    all_ok = True
    for text, vector in zip(TEXTS, vectors):
        actual_len = len(vector)
        ok = actual_len == DIMENSIONS
        all_ok = all_ok and ok
        print("文本: {} | 向量实际长度: {} | 是否为 {} 维: {}".format(
            text, actual_len, DIMENSIONS, "是" if ok else "否"))
        print("  前 5 个分量: {}".format(vector[:5]))

    print("-" * 40)
    if all_ok:
        print("校验通过: {} 条向量的实际长度均为 {}。".format(len(vectors), DIMENSIONS))
    else:
        print("校验失败: 存在向量长度不等于 {} 的情况。".format(DIMENSIONS))
        sys.exit(1)


if __name__ == "__main__":
    main()
