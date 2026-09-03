#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用两把智谱 Key 完成:
  1. embedding-3 计算两句话的余弦相似度        -> 只能走开放平台按量付费 (ZHIPUAI_API_KEY)
  2. glm-5.3 用一句话判断两句话意思是否相近    -> 优先走 GLM Coding Plan 套餐 (GLM_CODING_PLAN_API_KEY)

说明:
  - GLM Coding Plan 套餐额度只覆盖对话模型 (GLM 系列 chat), 且需要走 coding 专用端点:
        https://open.bigmodel.cn/api/coding/paas/v4
    embedding 模型不在套餐范围内, 所以 embedding-3 必须用开放平台按量付费 Key。
  - 对话调用优先用套餐 Key; 如果没设套餐 Key 或套餐端点调用失败, 自动回退到按量付费 Key。

运行: python3 main.py
"""

import math
import os
import sys

import requests

OPEN_BASE = "https://open.bigmodel.cn/api/paas/v4"           # 开放平台 (按量付费)
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"  # GLM Coding Plan 套餐专用端点

EMBEDDING_MODEL = "embedding-3"
CHAT_MODEL = "glm-5.3"

SENTENCE_A = "今天天气很好"
SENTENCE_B = "天气不错"

TIMEOUT = 60


def die(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def post_json(url: str, api_key: str, payload: dict) -> dict:
    resp = requests.post(url, headers=headers(api_key), json=payload, timeout=TIMEOUT)
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"HTTP {resp.status_code}, 非 JSON 响应: {resp.text[:300]}")
    if resp.status_code != 200 or "error" in data:
        err = data.get("error", data)
        raise RuntimeError(f"HTTP {resp.status_code}: {err}")
    return data


# ---------- 1. Embedding ----------

def get_embeddings(api_key: str, texts: list) -> list:
    data = post_json(
        f"{OPEN_BASE}/embeddings",
        api_key,
        {"model": EMBEDDING_MODEL, "input": texts},
    )
    items = sorted(data["data"], key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in items]


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------- 2. Chat ----------

def chat_once(base_url: str, api_key: str, prompt: str) -> str:
    data = post_json(
        f"{base_url}/chat/completions",
        api_key,
        {
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": False,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def chat_with_fallback(coding_key: str, open_key: str, prompt: str) -> str:
    """优先用套餐额度, 失败再回退到按量付费。"""
    if coding_key:
        try:
            reply = chat_once(CODING_BASE, coding_key, prompt)
            print("[info] 对话调用使用: GLM Coding Plan 套餐额度")
            return reply
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 套餐端点调用失败, 回退到按量付费: {e}", file=sys.stderr)
    if not open_key:
        die("没有可用的 Key 调用对话模型 (GLM_CODING_PLAN_API_KEY / ZHIPUAI_API_KEY 都不可用)")
    reply = chat_once(OPEN_BASE, open_key, prompt)
    print("[info] 对话调用使用: 开放平台按量付费")
    return reply


# ---------- main ----------

def main() -> None:
    coding_key = os.environ.get("GLM_CODING_PLAN_API_KEY", "").strip()
    open_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    if not open_key:
        die("未设置环境变量 ZHIPUAI_API_KEY (embedding-3 不在 Coding Plan 套餐内, 必须用按量付费 Key)")
    if not coding_key:
        print("[warn] 未设置 GLM_CODING_PLAN_API_KEY, 对话调用将全部走按量付费", file=sys.stderr)

    # 1) 余弦相似度 (按量付费 Key)
    try:
        vec_a, vec_b = get_embeddings(open_key, [SENTENCE_A, SENTENCE_B])
    except Exception as e:  # noqa: BLE001
        die(f"embedding-3 调用失败: {e}")
    sim = cosine_similarity(vec_a, vec_b)
    print(f"句子 A: {SENTENCE_A}")
    print(f"句子 B: {SENTENCE_B}")
    print(f"embedding-3 余弦相似度: {sim:.4f}")

    # 2) glm-5.3 判断 (优先套餐 Key)
    prompt = (
        f"下面两句话:\n"
        f"1. {SENTENCE_A}\n"
        f"2. {SENTENCE_B}\n"
        f"它们的向量余弦相似度为 {sim:.4f}。"
        f"请只用一句话说明这两句话的意思是否相近。"
    )
    try:
        reply = chat_with_fallback(coding_key, open_key, prompt)
    except Exception as e:  # noqa: BLE001
        die(f"{CHAT_MODEL} 调用失败: {e}")
    print(f"{CHAT_MODEL} 的判断: {reply}")


if __name__ == "__main__":
    main()
