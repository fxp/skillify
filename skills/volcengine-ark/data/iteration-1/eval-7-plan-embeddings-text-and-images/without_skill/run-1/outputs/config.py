"""集中读取环境变量配置。所有密钥只从环境变量 / .env 读取，绝不写入代码。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv 为可选依赖：没装也能直接用环境变量
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# 各模型原生维度；EMBED_DIM 留空时使用该值。
NATIVE_DIMS = {
    "doubao-embedding-vision-250615": 2048,
    "doubao-embedding-vision-250328": 3072,
    "doubao-embedding-large-text-250515": 2048,
    "doubao-embedding-large-text-240915": 4096,
    "doubao-embedding-text-240715": 2560,
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default_factory=lambda: _env("ARK_API_KEY"))
    base_url: str = field(
        default_factory=lambda: _env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    )
    backend: str = field(default_factory=lambda: _env("EMBED_BACKEND", "multimodal").lower())
    multimodal_model: str = field(
        default_factory=lambda: _env("ARK_MULTIMODAL_MODEL", "doubao-embedding-vision-250615")
    )
    text_model: str = field(
        default_factory=lambda: _env("ARK_TEXT_MODEL", "doubao-embedding-large-text-250515")
    )
    embed_dim_override: int | None = field(
        default_factory=lambda: int(_env("EMBED_DIM")) if _env("EMBED_DIM") else None
    )
    notes_dir: Path = field(default_factory=lambda: Path(_env("NOTES_DIR", "notes")))
    images_dir: Path = field(default_factory=lambda: Path(_env("IMAGES_DIR", "imgs")))
    index_dir: Path = field(default_factory=lambda: Path(_env("INDEX_DIR", ".index")))

    # 文本切块参数（按字符估算，中文约 1 字 ≈ 1~1.5 token，1500 字远低于 4096 token 上限）
    chunk_chars: int = 1500
    chunk_overlap: int = 200

    def __post_init__(self) -> None:
        if not self.api_key:
            raise RuntimeError("缺少 ARK_API_KEY，请在环境变量或 .env 中设置。")
        if self.backend not in ("multimodal", "text"):
            raise RuntimeError(f"EMBED_BACKEND 取值非法: {self.backend!r}（应为 multimodal 或 text）")

    @property
    def model(self) -> str:
        return self.multimodal_model if self.backend == "multimodal" else self.text_model

    @property
    def embed_dim(self) -> int:
        if self.embed_dim_override:
            return self.embed_dim_override
        # 接入点 ID（ep-xxx）查不到原生维度时给个保守默认值，索引构建时会以真实返回长度为准
        return NATIVE_DIMS.get(self.model, 2048)

    @property
    def supports_images(self) -> bool:
        return self.backend == "multimodal"
