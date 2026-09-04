"""
火山方舟 Agent Plan 向量化客户端（doubao-embedding-vision）。

入口 / 鉴权 / 模型三者必须配套（详见 NOTES.md）：
  Base URL : https://ark.cn-beijing.volces.com/api/plan/v3   （含 /plan，不要用 /api/v3）
  API Key  : Agent Plan 专属 Key（环境变量 ARK_AGENT_PLAN_API_KEY，与方舟 API Key 不通用）
  model    : "doubao-embedding-vision"（小写 Model Name；响应里会解析成 doubao-embedding-vision-251215）

为什么文本和图片都走 POST /embeddings/multimodal，而不是 OpenAI 形态的 /embeddings：
  * /embeddings 的 input 只接受字符串，图片必须走 /embeddings/multimodal；
  * 同一向量库的 Query 与 Corpus 必须用同一条路径、同一模型版本、同一维度产出；
  * 检索用的 `instructions`（Query 侧 / Corpus 侧不同）只在 multimodal 路径上有文档保证。
所以这里仍用 openai SDK 的 client（复用 base_url / Bearer 鉴权 / 超时），
但用 client.post() 直接打 multimodal 路径，并按 data.embedding（单对象，不是 data[0]）取值。
"""
from __future__ import annotations

import base64
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import openai
from openai import OpenAI

# --------------------------------------------------------------------------- 配置

ARK_PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
EMBEDDING_MODEL = "doubao-embedding-vision"

# dimensions 只能 1024 或 2048（默认 2048）。本项目默认 1024：本地笔记库体量小，
# 1024 维存储 / 计算减半，也是官方 Agent Plan 向量化配置（OpenViking）使用的值。
# 建库后不要再改；search.py 会校验 meta 里记录的维度。
DEFAULT_DIMENSIONS = int(os.environ.get("ARK_EMBED_DIMENSIONS", "1024"))
_ALLOWED_DIMENSIONS = (1024, 2048)

# 官方 instructions 模板（"跨模态问答：底库文本 + 图片" 场景）。{} 以外的固定文字不要改。
# Query 侧 Target_modality 取决于 *底库* 的模态：底库同时有独立的文本样本和图片样本 -> "text/image"。
QUERY_INSTRUCTIONS = (
    "Target_modality: text/image.\n"
    "Instruction:根据这个问题，找到能回答这个问题的相应文本或图片\n"
    "Query:"
)
CORPUS_TEXT_INSTRUCTIONS = "Instruction:Compress the text into one word.\nQuery:"
CORPUS_IMAGE_INSTRUCTIONS = "Instruction:Compress the image into one word.\nQuery:"

# 图片输入限制（文档原文）：单张 < 10 MB；Base64 请求体 <= 64 MB；扩展名 / MIME 必须与实际格式一致。
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".apng": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
_MAGIC = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
    "image/bmp": (b"BM",),
}

# 重试策略（errors-and-limits.md §7）：限流 / 5xx / 网络错误退避重试；
# QuotaExceeded（套餐 5h/周/月额度耗尽）、4xx 参数错误、401/404 不重试。
RETRYABLE_429_PREFIXES = (
    "RateLimitExceeded",
    "ModelAccount",          # ModelAccountRpm/Tpm/IpmRateLimitExceeded
    "APIAccountRpmRateLimitExceeded",
    "AccountRateLimitExceeded",
    "ServerOverloaded",
    "RequestBurstTooFast",
)
NON_RETRYABLE_429 = ("QuotaExceeded", "SetLimitExceeded")


class ArkEmbeddingError(RuntimeError):
    """向量化调用失败且不应重试（配置错误、额度耗尽、参数错误等）。"""


@dataclass
class EmbeddingResult:
    vector: np.ndarray          # float32，已 L2 归一化
    model: str                  # 响应里的实际模型版本，如 doubao-embedding-vision-251215
    prompt_tokens: int
    text_tokens: int
    image_tokens: int


# --------------------------------------------------------------------------- 客户端

def make_client(timeout: float = 60.0) -> OpenAI:
    api_key = os.environ.get("ARK_AGENT_PLAN_API_KEY")
    if not api_key:
        raise ArkEmbeddingError(
            "缺少环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 控制台 → 使用配置 → 第 3 步 配置专属 API Key）。"
            "注意：方舟 API Key / Coding Plan Key 打 /api/plan/v3 会 401。"
        )
    # max_retries=0：重试交给下面 _with_retry()，以便区分「可重试的限流」与「不可重试的额度耗尽」。
    return OpenAI(base_url=ARK_PLAN_BASE_URL, api_key=api_key, timeout=timeout, max_retries=0)


def _error_parts(exc: openai.APIStatusError) -> tuple[str, str]:
    """从方舟错误体 {"error": {"code", "message", "type"}} 里取 (code, message)。程序判别只看 code。"""
    body = exc.body if isinstance(exc.body, dict) else {}
    err = body.get("error") if isinstance(body.get("error"), dict) else body
    if not isinstance(err, dict):
        return "", str(exc)
    return str(err.get("code", "")), str(err.get("message", exc.message))


def _error_code(exc: openai.APIStatusError) -> str:
    return _error_parts(exc)[0]


def _with_retry(fn, *, max_attempts: int = 5, base_delay: float = 1.5):
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except openai.RateLimitError as e:          # HTTP 429
            code, msg = _error_parts(e)
            if code.startswith(NON_RETRYABLE_429) or attempt >= max_attempts:
                hint = ""
                if code.startswith("QuotaExceeded"):
                    hint = "（Agent Plan 5 小时 / 周 / 月额度耗尽：等 reset_time，或在控制台开启「超额后付费」）"
                raise ArkEmbeddingError(f"429 {code}: {msg}{hint}") from e
            if not code.startswith(RETRYABLE_429_PREFIXES):
                # 未知 429 子码：保守地也重试，但打印出来便于排查
                print(f"[warn] 未知 429 错误码 {code!r}，退避重试", flush=True)
        except (openai.InternalServerError, openai.APIConnectionError, openai.APITimeoutError) as e:
            if attempt >= max_attempts:
                raise ArkEmbeddingError(f"重试 {max_attempts} 次后仍失败: {e}") from e
        except openai.AuthenticationError as e:     # 401
            raise ArkEmbeddingError(
                "401 AuthenticationError：Key 与入口不配套。/api/plan/v3 只认 Agent Plan 专属 Key。"
            ) from e
        except openai.NotFoundError as e:           # 404
            code, msg = _error_parts(e)
            raise ArkEmbeddingError(
                f"404 {code}: {msg}（model 必须是套餐内的小写 Model Name，如 doubao-embedding-vision）"
            ) from e
        except openai.APIStatusError as e:          # 其余 4xx：参数错误、审核等，不重试
            code, msg = _error_parts(e)
            raise ArkEmbeddingError(f"{e.status_code} {code}: {msg}") from e
        # 指数退避 + 抖动
        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
        time.sleep(min(delay, 30))


# --------------------------------------------------------------------------- 输入构造

def validate_image(path: str | Path) -> tuple[str, bytes]:
    """校验本地图片是否满足方舟输入限制，返回 (mime, 原始字节)；不满足则抛 ArkEmbeddingError。"""
    path = Path(path)
    mime = IMAGE_MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        raise ArkEmbeddingError(f"不支持的图片扩展名: {path}")
    raw = path.read_bytes()
    if len(raw) >= MAX_IMAGE_BYTES:
        raise ArkEmbeddingError(f"图片超过 10MB 限制: {path} ({len(raw)} bytes)")
    magics = _MAGIC.get(mime, ())
    if magics and not any(raw.startswith(m) for m in magics):
        raise ArkEmbeddingError(f"图片实际格式与扩展名不一致（方舟要求二者一致）: {path}")
    return mime, raw


def image_to_data_url(path: str | Path) -> str:
    """把本地图片编码为 data:image/<fmt>;base64,...（先经 validate_image 校验）。"""
    mime, raw = validate_image(path)
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def text_item(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def image_item(path: str | Path) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": image_to_data_url(path)}}


# --------------------------------------------------------------------------- 向量化

def l2_normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-12)


def embed(
    client: OpenAI,
    item: dict[str, Any],
    instructions: str,
    *,
    dimensions: int = DEFAULT_DIMENSIONS,
    model: str = EMBEDDING_MODEL,
) -> EmbeddingResult:
    """
    对单条素材（一段文本或一张图）调用 POST /embeddings/multimodal，返回归一化后的稠密向量。

    注意：multimodal 接口会把整个 input[] 融合成 *一条* 向量（响应 data 是单对象），
    所以每条素材必须单独请求，这里 input 固定只放一个元素。
    """
    if dimensions not in _ALLOWED_DIMENSIONS:
        raise ArkEmbeddingError(f"dimensions 只能是 {_ALLOWED_DIMENSIONS}，收到 {dimensions}")

    body = {
        "model": model,
        "input": [item],
        "instructions": instructions,
        "dimensions": dimensions,
        "encoding_format": "float",
    }

    def _call():
        # cast_to=object -> 直接拿到 JSON dict；路径相对 base_url 拼接为 /api/plan/v3/embeddings/multimodal
        return client.post("/embeddings/multimodal", cast_to=object, body=body)

    resp: dict[str, Any] = _with_retry(_call)

    data = resp.get("data")
    if isinstance(data, dict):                 # 实测形态：data.embedding
        emb = data["embedding"]
    elif isinstance(data, list) and data:      # 文档另一处描述的列表形态，兜底
        emb = data[0]["embedding"]
    else:
        raise ArkEmbeddingError(f"无法解析响应 data 字段: {str(resp)[:300]}")

    vec = np.asarray(emb, dtype=np.float32)
    if vec.shape != (dimensions,):
        raise ArkEmbeddingError(f"返回维度 {vec.shape} 与请求的 dimensions={dimensions} 不一致")

    usage = resp.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return EmbeddingResult(
        vector=l2_normalize(vec),
        model=str(resp.get("model", model)),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        text_tokens=int(details.get("text_tokens", 0)),
        image_tokens=int(details.get("image_tokens", 0)),
    )


def embed_query(client: OpenAI, query: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> EmbeddingResult:
    return embed(client, text_item(query), QUERY_INSTRUCTIONS, dimensions=dimensions)


def embed_note_chunk(client: OpenAI, chunk: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> EmbeddingResult:
    return embed(client, text_item(chunk), CORPUS_TEXT_INSTRUCTIONS, dimensions=dimensions)


def embed_image(client: OpenAI, path: str | Path, *, dimensions: int = DEFAULT_DIMENSIONS) -> EmbeddingResult:
    return embed(client, image_item(path), CORPUS_IMAGE_INSTRUCTIONS, dimensions=dimensions)


def estimate_afp(text_tokens: int, image_tokens: int) -> float:
    """Agent Plan 向量化抵扣系数 0.5（输入）：AFP = tokens × 0.5 / 10000。仅用于日志估算。"""
    return (text_tokens + image_tokens) * 0.5 / 10_000
