#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
两把智谱 Key 的分工:
  - GLM_CODING_PLAN_API_KEY : GLM Coding Plan 套餐 Key,只能走 Coding 专用端点
                              https://open.bigmodel.cn/api/coding/paas/v4 ,只支持对话类模型。
  - ZHIPUAI_API_KEY         : 开放平台按量付费 Key,走通用端点
                              https://open.bigmodel.cn/api/paas/v4 ,支持 embedding 等全部接口。

因此:
  1. embedding-3 套餐不覆盖 → 必须用 ZHIPUAI_API_KEY(按量付费)。
  2. glm-5.3 对话     → 优先用 GLM_CODING_PLAN_API_KEY 走 Coding 端点(用套餐额度),
                        套餐 Key 不存在或调用失败时回退到 ZHIPUAI_API_KEY 走通用端点。

运行: python3 main.py
依赖: pip install requests
"""

import json
import math
import os
import sys

import requests

OPEN_BASE = "https://open.bigmodel.cn/api/paas/v4"
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"

EMBED_MODEL = "embedding-3"
CHAT_MODEL = "glm-5.3"

SENT_A = "今天天气很好"
SENT_B = "天气不错"

TIMEOUT = 60


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _post(url: str, api_key: str, payload: dict) -> dict:
    resp = requests.post(url, headers=_headers(api_key), json=payload, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} {url}\n{resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"API error {url}\n{json.dumps(data, ensure_ascii=False)}")
    return data


def get_embeddings(api_key: str, texts: list) -> list:
    """调用 embedding-3,返回与 texts 顺序一致的向量列表。"""
    data = _post(f"{OPEN_BASE}/embeddings", api_key, {"model": EMBED_MODEL, "input": texts})
    items = sorted(data["data"], key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in items]


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def chat_once(base: str, api_key: str, prompt: str) -> str:
    data = _post(
        f"{base}/chat/completions",
        api_key,
        {
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def main() -> int:
    coding_key = os.environ.get("GLM_CODING_PLAN_API_KEY", "").strip()
    open_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    # ---------- 1. Embedding(只能走按量付费 Key) ----------
    if not open_key:
        print("错误: 未设置 ZHIPUAI_API_KEY。embedding-3 不在 GLM Coding Plan 套餐范围内,"
              "必须使用开放平台按量付费 Key。", file=sys.stderr)
        return 1

    print(f"[1/2] 使用 ZHIPUAI_API_KEY(按量付费)调用 {EMBED_MODEL} ...")
    try:
        vec_a, vec_b = get_embeddings(open_key, [SENT_A, SENT_B])
    except Exception as e:  # noqa: BLE001
        print(f"Embedding 调用失败: {e}", file=sys.stderr)
        return 1

    sim = cosine_similarity(vec_a, vec_b)
    print(f"「{SENT_A}」 与 「{SENT_B}」 的余弦相似度: {sim:.4f}")
    print()

    # ---------- 2. Chat(优先套餐 Key,失败回退按量 Key) ----------
    prompt = (
        f"这两句话的意思是否相近?请只用一句话回答。\n"
        f"句子1:{SENT_A}\n句子2:{SENT_B}\n"
        f"(参考:它们的 embedding 余弦相似度为 {sim:.4f})"
    )

    answer = None
    if coding_key:
        print(f"[2/2] 使用 GLM_CODING_PLAN_API_KEY(套餐额度)调用 {CHAT_MODEL} ...")
        try:
            answer = chat_once(CODING_BASE, coding_key, prompt)
        except Exception as e:  # noqa: BLE001
            print(f"套餐 Key 调用失败,回退到按量付费 Key。原因: {e}", file=sys.stderr)
    else:
        print("[2/2] 未设置 GLM_CODING_PLAN_API_KEY,直接使用 ZHIPUAI_API_KEY(按量付费)"
              f"调用 {CHAT_MODEL} ...")

    if answer is None:
        try:
            answer = chat_once(OPEN_BASE, open_key, prompt)
        except Exception as e:  # noqa: BLE001
            print(f"Chat 调用失败: {e}", file=sys.stderr)
            return 1

    print(f"{CHAT_MODEL} 的判断: {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
