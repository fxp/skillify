"""用火山方舟 Agent Plan 给三段文本做向量化，维度指定 1024，并打印每条向量的实际长度。

接入要点（依据 volcengine-ark skill 实测结论，2026-09-04）：
- Agent Plan 专属入口：https://ark.cn-beijing.volces.com/api/plan/v3
  （勿用 /api/v3：Agent Plan 专属 Key 打 /api/v3 会 401，方舟 Key 打则产生额外费用）
- 鉴权：Authorization: Bearer $ARK_AGENT_PLAN_API_KEY（Agent Plan 专属 Key，与方舟 API Key 不通用）
- 模型：doubao-embedding-vision（Plan 入口用小写 Model Name，勿带日期后缀）
- 维度：不传 dimensions 默认 2048 维；传 dimensions: 1024 实测返回 1024 维
- input 只收字符串（OpenAI 形态实测），故逐条请求，每条文本对应一个向量

运行：export ARK_AGENT_PLAN_API_KEY=... && python3 main.py
"""

from __future__ import annotations

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"
MODEL = "doubao-embedding-vision"
DIMENSIONS = 1024

TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def get_api_key() -> str:
    key = os.environ.get("ARK_AGENT_PLAN_API_KEY", "").strip()
    if not key:
        sys.exit(
            "错误：未设置环境变量 ARK_AGENT_PLAN_API_KEY。"
            "请在 Agent Plan 控制台『使用配置 → 配置专属API Key』获取，"
            "然后 export ARK_AGENT_PLAN_API_KEY=<你的Key>"
        )
    return key


def embed_text(api_key: str, text: str) -> list[float]:
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": text,                # OpenAI 形态的 input 只收字符串
            "dimensions": DIMENSIONS,     # 不传则默认 2048 维
            "encoding_format": "float",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        hint = ""
        if resp.status_code == 401:
            hint = ("（提示：确认用的是 Agent Plan 专属 Key，且 Base URL 为 /api/plan/v3；"
                    "方舟 API Key 或 /api/v3、/api/coding 入口都会 401）")
        elif resp.status_code == 404:
            hint = "（提示：确认订阅套餐包含向量化模型 doubao-embedding-vision）"
        sys.exit(f"错误：embeddings 接口返回 {resp.status_code}: {resp.text}{hint}")
    data = resp.json()["data"]
    return data[0]["embedding"]


def main() -> None:
    api_key = get_api_key()
    print(f"模型: {MODEL}，请求维度: {DIMENSIONS}")
    print("-" * 40)
    for i, text in enumerate(TEXTS):
        vector = embed_text(api_key, text)
        ok = "符合预期" if len(vector) == DIMENSIONS else "不符合预期！"
        print(f"[{i}] {text} -> 向量实际长度: {len(vector)}（{ok}）")


if __name__ == "__main__":
    main()
