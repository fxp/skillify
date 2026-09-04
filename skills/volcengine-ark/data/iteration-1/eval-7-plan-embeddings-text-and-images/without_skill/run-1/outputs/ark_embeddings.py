"""火山方舟 Embedding 客户端封装（基于 openai Python SDK）。

两条通路：
1. 文本 embedding：/embeddings，OpenAI 兼容，直接用 client.embeddings.create（支持批量）。
2. 多模态 embedding：/embeddings/multimodal，方舟私有接口，OpenAI SDK 没有对应方法，
   这里复用 client.post() 走同一套 base_url / 鉴权 / 重试，只是自己解析响应。
   该接口一次请求只产出 **一个** 向量（一段文本、一张图、或图+文融合），
   且响应里 data 是单个对象而非数组——与 OpenAI 的 /embeddings 不同。
"""
from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import numpy as np
from openai import APIStatusError, OpenAI

from config import Settings

log = logging.getLogger(__name__)

# 方舟文本 embedding 单次请求最多 256 条输入
TEXT_BATCH_SIZE = 64
# 方舟对图片的大小限制（base64 前），保守取 10MB
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def l2_normalize(vecs: np.ndarray) -> np.ndarray:
    """按行做 L2 归一化；归一化后点积即余弦相似度。"""
    vecs = np.asarray(vecs, dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


class ArkEmbedder:
    def __init__(self, settings: Settings):
        self.s = settings
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
            max_retries=3,
        )

    # ------------------------------------------------------------------ 文本
    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        """把一批文本向量化，返回 shape=(n, dim) 的归一化 float32 数组。"""
        if not texts:
            return np.zeros((0, self.s.embed_dim), dtype=np.float32)
        if self.s.backend == "multimodal":
            # 统一向量空间：文本也走多模态模型，逐条请求
            return l2_normalize(np.stack([self._embed_multimodal(text=t) for t in texts]))
        return l2_normalize(self._embed_texts_openai(texts))

    def _embed_texts_openai(self, texts: Sequence[str]) -> np.ndarray:
        out: list[list[float]] = []
        for start in range(0, len(texts), TEXT_BATCH_SIZE):
            batch = list(texts[start : start + TEXT_BATCH_SIZE])
            kwargs: dict[str, Any] = dict(model=self.s.text_model, input=batch, encoding_format="float")
            if self.s.embed_dim_override:
                kwargs["dimensions"] = self.s.embed_dim_override
            resp = self.client.embeddings.create(**kwargs)
            # OpenAI 兼容：data 是数组，按 index 排序后取 embedding
            ordered = sorted(resp.data, key=lambda d: d.index)
            out.extend(d.embedding for d in ordered)
            log.debug("text batch %d..%d tokens=%s", start, start + len(batch), getattr(resp.usage, "total_tokens", "?"))
        return np.asarray(out, dtype=np.float32)

    # ------------------------------------------------------------------ 图片
    def embed_image(self, path: Path, caption: str | None = None) -> np.ndarray:
        """单张图片向量化（可选附带文字说明，图+文融合成一个向量）。"""
        if not self.s.supports_images:
            raise RuntimeError("EMBED_BACKEND=text 不支持图片，请切换为 multimodal。")
        return l2_normalize(self._embed_multimodal(text=caption, image_path=path))

    def embed_images(self, paths: Iterable[Path]) -> np.ndarray:
        vecs = [self.embed_image(p) for p in paths]
        if not vecs:
            return np.zeros((0, self.s.embed_dim), dtype=np.float32)
        return np.stack(vecs)

    # ------------------------------------------------------------------ 多模态底层
    def _embed_multimodal(self, text: str | None = None, image_path: Path | None = None) -> np.ndarray:
        if text is None and image_path is None:
            raise ValueError("text 和 image_path 至少提供一个")

        content: list[dict[str, Any]] = []
        if text:
            content.append({"type": "text", "text": text})
        if image_path is not None:
            content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}})

        body: dict[str, Any] = {
            "model": self.s.multimodal_model,
            "input": content,
            "encoding_format": "float",
        }

        try:
            raw = self.client.post(
                "/embeddings/multimodal",
                body=body,
                cast_to=httpx.Response,  # 拿原始响应自己解析，避开 SDK 对 data 数组的假设
            )
        except APIStatusError as e:
            log.error("multimodal embedding 失败 status=%s body=%s", e.status_code, e.body)
            raise
        payload = raw.json()
        vec = _extract_embedding(payload)

        # 客户端截断到目标维度（Matryoshka），随后由调用方归一化
        if self.s.embed_dim_override and len(vec) > self.s.embed_dim_override:
            vec = vec[: self.s.embed_dim_override]
        return np.asarray(vec, dtype=np.float32)


def _extract_embedding(payload: dict[str, Any]) -> list[float]:
    """兼容两种响应形状：
    - 方舟多模态：{"data": {"embedding": [...], "object": "embedding"}, "usage": {...}}
    - OpenAI 风格：{"data": [{"embedding": [...], "index": 0}], ...}
    """
    data = payload.get("data")
    if isinstance(data, dict):
        return data["embedding"]
    if isinstance(data, list) and data:
        return data[0]["embedding"]
    raise ValueError(f"无法从响应中解析 embedding: {str(payload)[:300]}")


def _image_to_data_url(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"{path} 大小 {size/1e6:.1f}MB 超过限制，请先压缩。")
    mime, _ = mimetypes.guess_type(path.name)
    if mime is None or not mime.startswith("image/"):
        mime = "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"
