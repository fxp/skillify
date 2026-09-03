#!/usr/bin/env python3
"""两把智谱 Key 协同使用示例：

1. 用 **开放平台按量付费 Key**（ZHIPUAI_API_KEY）调 `embedding-3`，
   计算「今天天气很好」和「天气不错」的余弦相似度。
   —— Embeddings 不在 GLM Coding Plan 套餐内，套餐 Key 调它必报 429/1113，只能走标准 Key。
2. 用 **GLM Coding Plan 套餐 Key**（GLM_CODING_PLAN_API_KEY）调 `glm-5.3`，
   让模型用一句话判断两句话意思是否相近。
   —— 对话是套餐包含的能力，走 Coding 端点即可消耗套餐额度；若没配套餐 Key 则自动回退到标准 Key。

两套体系的区别（Key 不通用、Base URL 不同）：
  标准 API      : https://open.bigmodel.cn/api/paas/v4          <- ZHIPUAI_API_KEY
  Coding Plan   : https://open.bigmodel.cn/api/coding/paas/v4   <- GLM_CODING_PLAN_API_KEY

用法：
  export ZHIPUAI_API_KEY=...            # 必需
  export GLM_CODING_PLAN_API_KEY=...    # 可选，有则对话走套餐额度
  python3 main.py
"""

import math
import os
import sys
import time

import requests

STANDARD_BASE = "https://open.bigmodel.cn/api/paas/v4"
CODING_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"

SENTENCE_A = "今天天气很好"
SENTENCE_B = "天气不错"

TIMEOUT = 120
MAX_RETRIES = 3


class BigModelError(RuntimeError):
    pass


def post_json(url: str, api_key: str, payload: dict) -> dict:
    """带指数退避的 POST；只对 429(限流/过载) 与 5xx 重试，4xx 配置错误直接抛出。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_err = f"网络错误: {exc}"
        else:
            if resp.ok:
                return resp.json()

            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text[:500]}
            err = body.get("error", {}) if isinstance(body, dict) else {}
            code = str(err.get("code", ""))
            msg = err.get("message", "") or str(body)
            last_err = f"HTTP {resp.status_code} code={code} message={msg}"

            # 1113: 余额不足/无可用资源包。对套餐 Key 来说通常是打错端点或调了套餐不含的能力，重试无意义。
            if code == "1113":
                raise BigModelError(
                    f"{last_err}\n"
                    "  提示：1113 并不一定是真的没钱——如果这是 Coding Plan 套餐 Key，"
                    "请确认 Base URL 是 …/api/coding/paas/v4，且调用的是套餐包含的能力"
                    "（embeddings/rerank 等不在套餐内，需用标准 Key）。"
                )
            # 只对 429（1302 限流 / 1305 过载 等）和 5xx 做退避重试
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise BigModelError(last_err)

        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(f"  [重试 {attempt}/{MAX_RETRIES - 1}] {last_err}，{wait}s 后重试…", file=sys.stderr)
            time.sleep(wait)

    raise BigModelError(f"重试 {MAX_RETRIES} 次仍失败: {last_err}")


def cosine_similarity(a, b) -> float:
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_embeddings(api_key: str, texts: list[str]) -> list[list[float]]:
    """标准 API：POST /paas/v4/embeddings，model=embedding-3。"""
    data = post_json(
        f"{STANDARD_BASE}/embeddings",
        api_key,
        {"model": "embedding-3", "input": texts},
    )
    # 按 index 对齐，不假设返回顺序
    items = sorted(data["data"], key=lambda d: d["index"])
    if len(items) != len(texts):
        raise BigModelError(f"embeddings 返回条数({len(items)})与输入({len(texts)})不一致")
    return [item["embedding"] for item in items]


def ask_glm(api_key: str, base_url: str, prompt: str) -> str:
    """POST {base}/chat/completions，model=glm-5.3。
    glm-5.3 强制思考、无法关闭，这里用 reasoning_effort=low 降低思考开销（两个端点都接受）。"""
    data = post_json(
        f"{base_url}/chat/completions",
        api_key,
        {
            "model": "glm-5.3",
            "messages": [{"role": "user", "content": prompt}],
            "reasoning_effort": "low",
            "max_tokens": 1024,
            "stream": False,
        },
    )
    choice = data["choices"][0]
    finish = choice.get("finish_reason")
    if finish not in (None, "stop", "length"):
        raise BigModelError(f"模型未正常结束，finish_reason={finish}")
    content = (choice["message"].get("content") or "").strip()
    if not content:
        raise BigModelError(f"模型返回空 content: {data}")
    return content


def main() -> int:
    std_key = os.environ.get("ZHIPUAI_API_KEY")
    plan_key = os.environ.get("GLM_CODING_PLAN_API_KEY")

    if not std_key:
        print("错误：未设置 ZHIPUAI_API_KEY（开放平台按量付费 Key）。"
              "embedding-3 不在 Coding Plan 套餐内，必须用标准 Key。", file=sys.stderr)
        return 1

    # ---------- 第一步：embedding-3 余弦相似度（标准 Key） ----------
    print(f"[1/2] 用 embedding-3（标准 API，ZHIPUAI_API_KEY）计算向量…")
    try:
        vec_a, vec_b = get_embeddings(std_key, [SENTENCE_A, SENTENCE_B])
    except BigModelError as exc:
        print(f"embeddings 调用失败: {exc}", file=sys.stderr)
        return 1
    sim = cosine_similarity(vec_a, vec_b)
    print(f"「{SENTENCE_A}」 vs 「{SENTENCE_B}」")
    print(f"余弦相似度 = {sim:.4f}  （向量维度 {len(vec_a)}）")
    print()

    # ---------- 第二步：glm-5.3 一句话判断（优先套餐 Key） ----------
    if plan_key:
        chat_key, chat_base, src = plan_key, CODING_BASE, "GLM Coding Plan 套餐额度"
    else:
        chat_key, chat_base, src = std_key, STANDARD_BASE, "标准 API 按量计费（未设置 GLM_CODING_PLAN_API_KEY）"
    print(f"[2/2] 用 glm-5.3（{src}）判断语义…")

    prompt = (
        f"下面两句话：\n"
        f"A：{SENTENCE_A}\n"
        f"B：{SENTENCE_B}\n"
        f"它们的 embedding 余弦相似度为 {sim:.4f}。"
        f"请只用一句话说明这两句话的意思是否相近，不要输出其他内容。"
    )
    try:
        answer = ask_glm(chat_key, chat_base, prompt)
    except BigModelError as exc:
        if plan_key:
            # 套餐额度用尽 / 套餐 Key 异常时，回退到标准 Key，保证脚本能跑通
            print(f"套餐调用失败，回退到标准 API: {exc}", file=sys.stderr)
            try:
                answer = ask_glm(std_key, STANDARD_BASE, prompt)
            except BigModelError as exc2:
                print(f"chat/completions 调用失败: {exc2}", file=sys.stderr)
                return 1
        else:
            print(f"chat/completions 调用失败: {exc}", file=sys.stderr)
            return 1

    print(f"glm-5.3：{answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
