#!/usr/bin/env python3
"""
两把智谱 Key 分工调用示例（纯 requests，直接打 HTTP）：

  1. embedding-3 计算两句话的余弦相似度
     -> 向量能力不在 GLM Coding Plan 套餐内，只能用开放平台按量付费 Key
        (ZHIPUAI_API_KEY) 打标准端点 https://open.bigmodel.cn/api/paas/v4
  2. glm-5.3 用一句话判断两句话意思是否相近
     -> 对话能力套餐包含，优先用套餐 Key (GLM_CODING_PLAN_API_KEY)
        打 Coding 端点 https://open.bigmodel.cn/api/coding/paas/v4，走套餐额度；
        套餐 Key 没配或套餐额度不可用(1113)时自动回退到按量付费 Key。

注意：套餐 Key 打标准端点、或用套餐 Key 调 embeddings，都会报 429 + 1113
"余额不足"，这不是要充值，而是 Key / 端点 / 能力不匹配。

运行：python3 main.py
"""

from __future__ import annotations

import math
import os
import sys

import requests

STANDARD_BASE = "https://open.bigmodel.cn/api/paas/v4"          # 开放平台按量付费
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"     # GLM Coding Plan 套餐

SENTENCE_A = "今天天气很好"
SENTENCE_B = "天气不错"

TIMEOUT = 120


def env_key(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def post_json(base_url: str, path: str, api_key: str, payload: dict) -> requests.Response:
    return requests.post(
        f"{base_url}/{path}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=TIMEOUT,
    )


def error_code(resp: requests.Response) -> str | None:
    """从错误响应体里取智谱业务错误码（如 "1113"），取不到返回 None。"""
    try:
        return str(resp.json().get("error", {}).get("code"))
    except Exception:
        return None


def describe_error(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return f"HTTP {resp.status_code}, code={err.get('code')}, message={err.get('message')}"
    except Exception:
        return f"HTTP {resp.status_code}, body={resp.text[:300]}"


# ---------------------------------------------------------------------------
# 1. Embeddings（只能走标准 Key）
# ---------------------------------------------------------------------------
def get_embeddings(texts: list[str], api_key: str) -> list[list[float]]:
    resp = post_json(
        STANDARD_BASE,
        "embeddings",
        api_key,
        {"model": "embedding-3", "input": texts, "dimensions": 1024},
    )
    if not resp.ok:
        raise RuntimeError(f"embeddings 调用失败: {describe_error(resp)}")
    data = resp.json()["data"]
    # 按 index 对齐，不假设返回顺序
    ordered = sorted(data, key=lambda item: item["index"])
    return [item["embedding"] for item in ordered]


def cosine_similarity(u: list[float], v: list[float]) -> float:
    dot = sum(a * b for a, b in zip(u, v))
    norm_u = math.sqrt(sum(a * a for a in u))
    norm_v = math.sqrt(sum(b * b for b in v))
    if norm_u == 0 or norm_v == 0:
        return 0.0
    return dot / (norm_u * norm_v)


# ---------------------------------------------------------------------------
# 2. Chat（优先套餐 Key + Coding 端点，失败回退标准 Key + 标准端点）
# ---------------------------------------------------------------------------
def chat_once(base_url: str, api_key: str, prompt: str) -> tuple[str, str]:
    resp = post_json(
        base_url,
        "chat/completions",
        api_key,
        {
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": prompt}],
            # glm-5.3 在标准端点无法关闭思考，用 low 档把思考开销降到最低；
            # 这个参数在 Coding 端点同样可用，两端点通用。
            "reasoning_effort": "low",
            "max_tokens": 256,
            "stream": False,
        },
    )
    if not resp.ok:
        raise RuntimeError(describe_error(resp))
    body = resp.json()
    message = body["choices"][0]["message"]
    content = (message.get("content") or "").strip()
    actual_model = body.get("model", "glm-5.3")
    return content, actual_model


def judge_similarity(prompt: str, plan_key: str | None, standard_key: str | None) -> str:
    attempts = []
    if plan_key:
        attempts.append(("GLM Coding Plan 套餐额度", CODING_BASE, plan_key))
    if standard_key:
        attempts.append(("开放平台按量付费", STANDARD_BASE, standard_key))
    if not attempts:
        raise RuntimeError("没有可用的对话 Key（GLM_CODING_PLAN_API_KEY / ZHIPUAI_API_KEY 都未设置）")

    last_error = None
    for label, base_url, key in attempts:
        try:
            content, actual_model = chat_once(base_url, key, prompt)
            print(f"[对话] 使用 {label}（{base_url}，实际模型 {actual_model}）")
            return content
        except RuntimeError as exc:
            last_error = exc
            print(f"[对话] {label} 调用失败：{exc}", file=sys.stderr)
            if "1113" in str(exc) and label.startswith("GLM Coding Plan"):
                print("[对话] 套餐额度不可用（1113），回退到按量付费 Key……", file=sys.stderr)
    raise RuntimeError(f"glm-5.3 调用失败: {last_error}")


def main() -> int:
    plan_key = env_key("GLM_CODING_PLAN_API_KEY")
    standard_key = env_key("ZHIPUAI_API_KEY")

    if not standard_key:
        print(
            "错误：未设置 ZHIPUAI_API_KEY。embedding-3 不在 GLM Coding Plan 套餐内，"
            "必须用开放平台按量付费 Key 调用。",
            file=sys.stderr,
        )
        return 1
    if not plan_key:
        print(
            "提示：未设置 GLM_CODING_PLAN_API_KEY，对话将改用 ZHIPUAI_API_KEY 按量计费。",
            file=sys.stderr,
        )

    # ---- 1. 余弦相似度（标准 Key）----
    print(f"[向量] 使用开放平台按量付费 Key 调用 embedding-3（{STANDARD_BASE}）")
    vec_a, vec_b = get_embeddings([SENTENCE_A, SENTENCE_B], standard_key)
    score = cosine_similarity(vec_a, vec_b)
    print(f"「{SENTENCE_A}」与「{SENTENCE_B}」的余弦相似度：{score:.4f}")

    # ---- 2. glm-5.3 一句话判断（优先套餐 Key）----
    prompt = (
        f"下面两句话的意思是否相近？请只用一句话回答，不要展开。\n"
        f"第一句：{SENTENCE_A}\n"
        f"第二句：{SENTENCE_B}\n"
        f"（参考：两句话的向量余弦相似度为 {score:.4f}）"
    )
    answer = judge_similarity(prompt, plan_key, standard_key)
    print(f"glm-5.3 的判断：{answer}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.RequestException as exc:
        print(f"网络请求异常：{exc}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
