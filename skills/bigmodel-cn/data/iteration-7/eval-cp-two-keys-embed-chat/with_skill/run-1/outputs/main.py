#!/usr/bin/env python3
"""
两把智谱 Key 的分工示例：
  - embedding-3 向量化：套餐不含 embeddings（打任何端点都会 429 + 1113），
    必须用开放平台按量付费 Key（ZHIPUAI_API_KEY）走标准端点 …/api/paas/v4。
  - glm-5.3 对话：套餐包含 glm-5.3，用 GLM Coding Plan Key（GLM_CODING_PLAN_API_KEY）
    走 Coding 端点 …/api/coding/paas/v4，消耗套餐额度而不是账户余额。
    若没配套餐 Key，则自动退回标准 Key + 标准端点。

依赖：pip install requests
运行：python3 main.py
"""
import math
import os
import sys
import time

import requests

# ---- 两套彼此隔离的 Key / Base URL，不能混用 ----
STANDARD_BASE = "https://open.bigmodel.cn/api/paas/v4"          # 按量付费 Key
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"     # GLM Coding Plan Key

STANDARD_KEY = os.environ.get("ZHIPUAI_API_KEY")
CODING_KEY = os.environ.get("GLM_CODING_PLAN_API_KEY")

SENTENCE_A = "今天天气很好"
SENTENCE_B = "天气不错"
TIMEOUT = 120


def post_json(url: str, api_key: str, payload: dict, retries: int = 3) -> dict:
    """带指数退避的 POST；对 1113 给出针对 Key/端点的明确提示，而不是笼统的“请充值”。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(retries):
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json()

        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code = str(err.get("code", ""))
        msg = err.get("message", resp.text[:200])
        last_err = f"HTTP {resp.status_code} code={code} message={msg} url={url}"

        if code == "1113":
            # 余额不足/无资源包：Key 与端点/能力不匹配时也是这个码，不要盲目充值
            raise RuntimeError(
                last_err
                + "\n提示：1113 通常不是真的没钱。请依次检查："
                "① 套餐 Key 只能打 …/api/coding/paas/v4；"
                "② embeddings/rerank 等能力不在套餐内，必须用 ZHIPUAI_API_KEY；"
                "③ 套餐 Key 只支持 glm-5.3 / glm-5.3-flash。"
            )
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            wait = 2 ** attempt
            print(f"  [retry] {last_err}，{wait}s 后重试…", file=sys.stderr)
            time.sleep(wait)
            continue
        break
    raise RuntimeError(last_err)


def cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embed(texts: list) -> list:
    """embedding-3 只能走标准 Key + 标准端点。"""
    if not STANDARD_KEY:
        sys.exit("缺少环境变量 ZHIPUAI_API_KEY：embedding-3 不在 GLM Coding Plan 套餐内，必须用开放平台按量付费 Key。")
    data = post_json(
        f"{STANDARD_BASE}/embeddings",
        STANDARD_KEY,
        {"model": "embedding-3", "input": texts, "dimensions": 1024},
    )
    # 按 index 对齐，不假设返回顺序
    ordered = sorted(data["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in ordered]


def chat(prompt: str) -> str:
    """glm-5.3 优先走套餐额度（Coding 端点），没有套餐 Key 时退回标准 Key。"""
    if CODING_KEY:
        base, key, via = CODING_BASE, CODING_KEY, "GLM Coding Plan 套餐额度"
    elif STANDARD_KEY:
        base, key, via = STANDARD_BASE, STANDARD_KEY, "开放平台按量付费（未检测到 GLM_CODING_PLAN_API_KEY）"
    else:
        sys.exit("缺少环境变量 GLM_CODING_PLAN_API_KEY / ZHIPUAI_API_KEY，无法调用 glm-5.3。")
    print(f"[chat] 使用 {via} 调用 glm-5.3")
    data = post_json(
        f"{base}/chat/completions",
        key,
        {
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": prompt}],
            # glm-5.3 强制思考，标准端点不允许 disabled；用 low 把思考开销压到最低
            "reasoning_effort": "low",
            "max_tokens": 256,
            "stream": False,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def main() -> None:
    # 1) embedding-3 余弦相似度（标准 Key）
    print(f"[embed] 使用开放平台按量付费 Key 调用 embedding-3")
    vec_a, vec_b = embed([SENTENCE_A, SENTENCE_B])
    sim = cosine_similarity(vec_a, vec_b)
    print(f"「{SENTENCE_A}」与「{SENTENCE_B}」的余弦相似度：{sim:.4f}")

    # 2) glm-5.3 一句话判断（优先套餐 Key）
    prompt = (
        f"“{SENTENCE_A}”和“{SENTENCE_B}”这两句话意思是否相近？"
        f"（它们的 embedding 余弦相似度为 {sim:.4f}）请只用一句话回答。"
    )
    answer = chat(prompt)
    print(f"glm-5.3：{answer}")


if __name__ == "__main__":
    main()
