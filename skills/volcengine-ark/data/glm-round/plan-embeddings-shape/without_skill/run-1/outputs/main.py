"""火山方舟（Agent Plan）文本向量化示例。

把三段文本通过方舟多模态向量化 API（Embeddings Multimodal API）转为
1024 维向量，并打印每条向量的实际长度进行确认。

- 接口：POST https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal
- 鉴权：Authorization: Bearer $ARK_AGENT_PLAN_API_KEY（Agent Plan 使用标准数据面地址）
- 维度：请求体的 dimensions 参数指定输出维度，取值 1024 或 2048（注意不是 dim）
- 输入：input 为对象数组，纯文本用 {"type": "text", "text": ...}
- 响应：data 数组中每项的 embedding 字段是 float 列表，顺序与 input 一致
"""

import os
import sys

import requests

API_KEY_ENV = "ARK_AGENT_PLAN_API_KEY"
EMBEDDINGS_URL = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"
MODEL_ID = "doubao-embedding-vision-251215"
DIMENSIONS = 1024

TEXTS = ["今天天气很好", "这部电影非常精彩", "服务器响应超时了"]


def get_embeddings(texts, api_key):
    """调用方舟向量化接口，返回与 texts 顺序一致的向量列表。"""
    payload = {
        "model": MODEL_ID,
        "input": [{"type": "text", "text": t} for t in texts],
        "encoding_format": "float",
        "dimensions": DIMENSIONS,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(EMBEDDINGS_URL, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        # 带上服务端返回的错误信息，便于排查（Key 无效、模型无权限、参数不合法等）
        raise RuntimeError(f"调用向量化接口失败：HTTP {resp.status_code} {resp.text}")
    return resp.json()["data"]


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"请先设置环境变量 {API_KEY_ENV}，例如：export {API_KEY_ENV}=ark-xxxx")

    try:
        data = get_embeddings(TEXTS, api_key)
    except requests.RequestException as exc:
        sys.exit(f"网络请求异常：{exc}")
    except RuntimeError as exc:
        sys.exit(str(exc))

    if len(data) != len(TEXTS):
        sys.exit(f"返回向量数量 {len(data)} 与输入数量 {len(TEXTS)} 不一致")

    # 响应 data 顺序与 input 一致；若带 index 字段则按 index 对齐
    if all("index" in item for item in data):
        data = sorted(data, key=lambda item: item["index"])

    print(f"模型：{MODEL_ID}，请求维度：{DIMENSIONS}")
    all_match = True
    for i, item in enumerate(data):
        embedding = item["embedding"]
        actual_dim = len(embedding)
        all_match = all_match and actual_dim == DIMENSIONS
        print(f"[{i}] {TEXTS[i]!r} -> 向量实际长度：{actual_dim}（前 3 维：{embedding[:3]}）")

    if all_match:
        print(f"确认：{len(data)} 条向量全部为 {DIMENSIONS} 维。")
    else:
        sys.exit(f"校验失败：存在实际长度不等于 {DIMENSIONS} 的向量。")


if __name__ == "__main__":
    main()
