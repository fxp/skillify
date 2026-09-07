"""火山方舟 Agent Plan 文本向量化：三段文本 -> 1024 维向量，并核对每条实际长度。

入口/模型依据（Agent Plan 专属，与方舟 API Key 不通用）：
- Base URL: https://ark.cn-beijing.volces.com/api/plan/v3（打 /api/v3 会 401）
- Endpoint: POST /embeddings（OpenAI 形态，input 只收字符串，响应取 data[0].embedding）
- model 填 Plan 入口的 Model Name: doubao-embedding-vision（实际解析到 doubao-embedding-vision-251215）
- dimensions 不传默认 2048，传 1024 生效（以上均经真实 API 验证）
"""

import os
import sys

import requests

BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"
MODEL = "doubao-embedding-vision"
DIMENSIONS = 1024
TIMEOUT = 60
TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def embed_text(text: str, api_key: str) -> list:
    """单条文本向量化，返回浮点向量。

    /embeddings 的 input 传对象数组会 400 "expected a string"，所以逐条字符串请求。
    """
    resp = requests.post(
        EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "input": text, "dimensions": DIMENSIONS},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        # 方舟错误体形如 {"error": {"code": ..., "message": ...}}，原样打出便于排查
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    data = resp.json()["data"]
    # OpenAI 形态 data 是数组；兼容 data 为单对象（/embeddings/multimodal 的形态）
    if isinstance(data, dict):
        return data["embedding"]
    return data[0]["embedding"]


def main() -> None:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        sys.exit(
            "错误：未设置环境变量 ARK_AGENT_PLAN_API_KEY"
            "（Agent Plan 专属 API Key，在 Agent Plan 控制台『使用配置』页获取）"
        )

    print(f"模型: {MODEL}，请求维度: {DIMENSIONS}")
    all_ok = True
    try:
        for i, text in enumerate(TEXTS):
            vec = embed_text(text, api_key)
            ok = len(vec) == DIMENSIONS
            all_ok = all_ok and ok
            status = "一致" if ok else "不一致!"
            print(f"[{i}] {text} -> 向量实际长度 {len(vec)}（期望 {DIMENSIONS}，{status}）")
    except requests.RequestException as exc:
        sys.exit(f"请求失败：{exc}")
    except RuntimeError as exc:
        sys.exit(f"向量化失败：{exc}")

    if all_ok:
        print(f"共 {len(TEXTS)} 条向量，长度全部为 {DIMENSIONS} ✅")
    else:
        sys.exit("存在向量长度与期望不符 ❌")


if __name__ == "__main__":
    main()
