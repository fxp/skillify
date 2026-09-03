#!/usr/bin/env python3
"""
两把智谱 Key 的分工示例：
  - embedding-3 计算句子余弦相似度  -> 走开放平台按量付费 (ZHIPUAI_API_KEY)
    （GLM Coding Plan 套餐只覆盖对话/编码模型，不包含 Embedding，所以这里只能按量付费）
  - glm-5.3 用一句话点评           -> 优先走 GLM Coding Plan 套餐 (GLM_CODING_PLAN_API_KEY)
    套餐 Key 缺失时自动回退到按量付费 Key。

运行： python3 main.py
依赖： pip install requests
"""

import math
import os
import sys

import requests

# 开放平台（按量付费）通用接口
OPEN_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# GLM Coding Plan 套餐专用接口（OpenAI 兼容格式）
CODING_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

EMBED_MODEL = "embedding-3"
CHAT_MODEL = "glm-5.3"
TIMEOUT = 60

SENTENCE_A = "今天天气很好"
SENTENCE_B = "天气不错"


def die(msg: str) -> None:
    print(f"[错误] {msg}", file=sys.stderr)
    sys.exit(1)


def post_json(url: str, api_key: str, payload: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    if resp.status_code != 200:
        die(f"HTTP {resp.status_code} 调用 {url} 失败：{resp.text[:500]}")
    data = resp.json()
    if "error" in data:
        die(f"接口返回错误：{data['error']}")
    return data


def get_embeddings(api_key: str, texts: list[str]) -> list[list[float]]:
    data = post_json(
        f"{OPEN_BASE_URL}/embeddings",
        api_key,
        {"model": EMBED_MODEL, "input": texts},
    )
    items = sorted(data["data"], key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in items]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def chat_once(base_url: str, api_key: str, prompt: str) -> str:
    data = post_json(
        f"{base_url}/chat/completions",
        api_key,
        {
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def main() -> None:
    coding_key = os.environ.get("GLM_CODING_PLAN_API_KEY", "").strip()
    open_key = os.environ.get("ZHIPUAI_API_KEY", "").strip()

    # 1) Embedding：套餐不含 embedding，必须用按量付费 Key
    if not open_key:
        die("未设置 ZHIPUAI_API_KEY（embedding-3 只能走开放平台按量付费）。")

    print(f"[1/2] 使用 {EMBED_MODEL}（开放平台按量付费）计算余弦相似度 ...")
    vec_a, vec_b = get_embeddings(open_key, [SENTENCE_A, SENTENCE_B])
    sim = cosine_similarity(vec_a, vec_b)
    print(f"「{SENTENCE_A}」与「{SENTENCE_B}」的余弦相似度：{sim:.4f}")

    # 2) 对话：优先走 Coding Plan 套餐额度，没有再回退按量付费
    if coding_key:
        chat_base, chat_key, source = CODING_BASE_URL, coding_key, "GLM Coding Plan 套餐"
    else:
        chat_base, chat_key, source = OPEN_BASE_URL, open_key, "开放平台按量付费（未设置套餐 Key，已回退）"

    print(f"\n[2/2] 使用 {CHAT_MODEL}（{source}）判断语义是否相近 ...")
    prompt = (
        f"下面两句话的余弦相似度为 {sim:.4f}。\n"
        f"句子一：{SENTENCE_A}\n"
        f"句子二：{SENTENCE_B}\n"
        "请只用一句话说明这两句话的意思是否相近。"
    )
    answer = chat_once(chat_base, chat_key, prompt)
    print(f"{CHAT_MODEL} 的回答：{answer}")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        die(f"网络请求异常：{e}")
    except (KeyError, IndexError, ValueError) as e:
        die(f"解析响应失败：{e}")
