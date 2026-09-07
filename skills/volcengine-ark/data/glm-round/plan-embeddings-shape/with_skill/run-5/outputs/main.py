"""火山方舟 Agent Plan 文本向量化示例。

用 Agent Plan 专属入口（/api/plan/v3）的 OpenAI 形态 embeddings 接口，
把三段中文文本编码成 1024 维向量，并打印每条向量的实际长度做确认。

运行前：export ARK_AGENT_PLAN_API_KEY=<Agent Plan 专属 API Key>
运行：python3 main.py
"""

import os
import sys

import requests

# Agent Plan 专属 Base URL（含 /plan）。勿混用 /api/v3 或 /api/coding/v3，
# 专属 Key 打过去不是走后付费，而是直接 401 AuthenticationError。
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBED_URL = f"{BASE_URL}/embeddings"

# Plan 入口的向量化模型填小写 Model Name（不带日期后缀），响应会回显具体版本
# （doubao-embedding-vision-251215）
MODEL = "doubao-embedding-vision"

# 维度只支持 1024 / 2048，不传默认 2048
DIMENSIONS = 1024

TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def embed_text(api_key: str, text: str) -> list:
    """对单条文本做向量化，返回 embedding 浮点数列表。

    input 只传单个字符串：这是 Plan 入口实测可用的形态
    （传多模态对象数组会报 400 "expected a string"，字符串数组形态官方未验证）。
    """
    resp = requests.post(
        EMBED_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,
            "dimensions": DIMENSIONS,
        },
        timeout=60,
    )
    if not resp.ok:
        # 方舟的错误详情在响应体里，原样带出来便于排查
        # （Key 无效 → 401 AuthenticationError；模型名/套餐不支持 → 404 UnsupportedModel）
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    # OpenAI 形态响应的 data 是数组，单条输入取 data[0].embedding
    return resp.json()["data"][0]["embedding"]


def main() -> None:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not api_key:
        sys.exit(
            "请先设置环境变量 ARK_AGENT_PLAN_API_KEY"
            "（在 Agent Plan 控制台「使用配置 → 配置专属API Key」获取，与方舟 API Key 不通用）"
        )

    print(f"模型: {MODEL}  目标维度: {DIMENSIONS}")
    all_ok = True
    for i, text in enumerate(TEXTS, 1):
        vector = embed_text(api_key, text)
        ok = len(vector) == DIMENSIONS
        all_ok = all_ok and ok
        status = "OK" if ok else f"不符合预期（应为 {DIMENSIONS}）"
        print(f"[{i}] 「{text}」 向量实际长度: {len(vector)}  {status}")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
