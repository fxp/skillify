#!/usr/bin/env python3
"""
用火山方舟 Agent Plan 套餐额度批量生图，并（在套餐档位允许时）把第一张图做成 5 秒视频。

  prompts.txt 每行一条文案  ->  out/NNN-<slug>.png  (+ out/manifest.jsonl)
  第一张图                  ->  out/video-001.mp4   (仅 Large / Max 套餐可用；Medium 会被服务端 404 拒绝并自动跳过)

入口 / Key / 模型 三件事必须配套，否则要么 401，要么额度不生效：
  Base URL : https://ark.cn-beijing.volces.com/api/plan/v3   （不是 /api/v3，那个会走后付费扣余额）
  Key      : 环境变量 ARK_AGENT_PLAN_API_KEY（Agent Plan 控制台"配置专属 API Key"，与方舟 API Key 不通用）
  model    : 小写 Model Name，图片 doubao-seedream-5.0-lite，视频 doubao-seedance-2.0-mini 等

用法：
  export ARK_AGENT_PLAN_API_KEY=...
  python generate.py                       # 读 ./prompts.txt，写 ./out/
  python generate.py --dry-run             # 只估算 AFP 消耗，不发请求
  python generate.py --size 2k --downscale 1024 --concurrency 2
  python generate.py --skip-video          # 只生图
  python generate.py --video-only --video-from out/001-xxx.png   # 只用已有图片再试一次视频

详细说明见同目录 NOTES.md。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import requests

# ----------------------------------------------------------------------------
# 常量：全部来自 Agent Plan 入口的实测/文档口径
# ----------------------------------------------------------------------------
PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
KEY_ENV = "ARK_AGENT_PLAN_API_KEY"

IMAGE_MODEL = "doubao-seedream-5.0-lite"      # Agent Plan 内唯一的生图模型
IMAGE_AFP_PER_IMAGE = 99                      # 每张成功图固定 99 AFP，与像素无关
IMAGE_SIZE_DEFAULT = "2k"                     # 5.0-lite 只认 2k / 3k / 4k / WIDTHxHEIGHT；"1K" 实测 400
IMAGE_MIN_PIXELS = 2560 * 1440                # 5.0-lite 像素下限 3,686,400
IMAGE_MAX_PIXELS = 4096 * 4096

VIDEO_MODEL_DEFAULT = "doubao-seedance-2.0-mini"  # 2.0 系列最便宜；仅 Large / Max 套餐可用
VIDEO_DURATION_DEFAULT = 5
VIDEO_RESOLUTION_DEFAULT = "720p"
# AFP / 万 token（不含输入视频）：2.0 480p/720p 230，2.0-fast 185，2.0-mini 115；1.5-pro 无声 36 / 有声 72
VIDEO_AFP_PER_10K_TOKENS = {
    "doubao-seedance-2.0": 230,
    "doubao-seedance-2.0-fast": 185,
    "doubao-seedance-2.0-mini": 115,
    "doubao-seedance-1.5-pro": 36,
}
RESOLUTION_PIXELS = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}

# Medium 档：月 100,000 AFP；图片 / 视频只受"日额度 = 月额度一半"与月额度约束，不受 5 小时 / 周限额
PLAN_TIER_MONTHLY_AFP = {"small": 20_000, "medium": 100_000, "large": 250_000, "max": 500_000}

HTTP_TIMEOUT_IMAGE = 300     # 一张 2k 图通常十几秒到一分钟
HTTP_TIMEOUT_DEFAULT = 60
VIDEO_POLL_INTERVAL = 10     # 查询接口 QPS 上限 20，勿高频轮询
VIDEO_MAX_WAIT = 1800

# 可退避重试的错误码（限流不计费，可放心重试）；其余 4xx 一律不重试
RETRYABLE_CODE_PREFIXES = (
    "RateLimitExceeded",
    "ModelAccount",            # ModelAccountRpm/Tpm/IpmRateLimitExceeded
    "APIAccountRpmRateLimitExceeded",
    "AccountRateLimitExceeded",
    "ServerOverloaded",
    "RequestBurstTooFast",
    "InternalServiceError",
)


# ----------------------------------------------------------------------------
# 错误类型
# ----------------------------------------------------------------------------
class ArkError(Exception):
    """方舟数据面错误：body 固定为 {"error":{"code","message","param","type"}}，判别只用 code。"""

    def __init__(self, status: int, code: str, message: str, param: str = "", body: Any = None):
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.param = param
        self.body = body

    @property
    def is_unsupported_model(self) -> bool:
        return self.status == 404 and self.code == "UnsupportedModel"

    @property
    def is_plan_quota_exhausted(self) -> bool:
        # 429 QuotaExceeded + "You have exceeded the 5-hour/weekly/monthly usage quota..."：等 reset_time，不能重试
        return self.code == "QuotaExceeded" and "usage quota" in self.message

    @property
    def is_queue_quota(self) -> bool:
        # 429 QuotaExceeded + "The request has exceeded the quota"：异步任务排队数超限，等在途任务完成后可重试
        return self.code == "QuotaExceeded" and "usage quota" not in self.message

    @property
    def retryable(self) -> bool:
        if self.status >= 500:
            return True
        if self.status == 429:
            if self.is_plan_quota_exhausted:
                return False
            if self.is_queue_quota:
                return True
            return self.code.startswith(RETRYABLE_CODE_PREFIXES)
        return False


# ----------------------------------------------------------------------------
# HTTP 客户端
# ----------------------------------------------------------------------------
class ArkPlanClient:
    def __init__(self, api_key: str, base_url: str = PLAN_BASE_URL, max_retries: int = 4):
        if "/api/v3" in base_url and "/api/plan/" not in base_url:
            # 控制台原话：请勿使用 /api/v3，接入会产生额外费用（Agent Plan Key 打过去实测是 401，但别赌）
            raise SystemExit(f"拒绝使用 {base_url}：Agent Plan 必须走 {PLAN_BASE_URL}")
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    @staticmethod
    def _parse_error(resp: requests.Response) -> ArkError:
        text = resp.text or ""
        if not text.strip():
            # /api/plan/v3 下不存在的路径返回 404 且 body 为空，没有 error 对象
            return ArkError(resp.status_code, "EmptyBody", f"empty response body for {resp.request.method} {resp.url}")
        try:
            body = resp.json()
        except ValueError:
            return ArkError(resp.status_code, "NonJSONBody", text[:500])
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict):
            return ArkError(resp.status_code, "UnknownError", text[:500], body=body)
        return ArkError(
            resp.status_code,
            str(err.get("code") or "UnknownError"),
            str(err.get("message") or ""),
            str(err.get("param") or ""),
            body=body,
        )

    def request(self, method: str, path: str, json_body: Optional[dict] = None, timeout: int = HTTP_TIMEOUT_DEFAULT) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.request(method, url, json=json_body, timeout=timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt > self.max_retries:
                    raise
                delay = self._backoff(attempt)
                log(f"  网络错误 {type(exc).__name__}，{delay:.1f}s 后重试（{attempt}/{self.max_retries}）")
                time.sleep(delay)
                continue

            if 200 <= resp.status_code < 300:
                try:
                    return resp.json()
                except ValueError:
                    raise ArkError(resp.status_code, "NonJSONBody", resp.text[:500])

            err = self._parse_error(resp)
            if err.retryable and attempt <= self.max_retries:
                delay = self._backoff(attempt)
                log(f"  {err.code}（HTTP {err.status}），{delay:.1f}s 后重试（{attempt}/{self.max_retries}）")
                time.sleep(delay)
                continue
            raise err

    @staticmethod
    def _backoff(attempt: int) -> float:
        # 指数退避 + 抖动，起始 1–2s，上限 30s
        return min(30.0, (2 ** (attempt - 1)) * (1.0 + random.random()))


# ----------------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load_prompts(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"找不到 {path}；每行一条文案，空行与 # 开头的行会被忽略")
    prompts: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prompts.append(line)
    if not prompts:
        raise SystemExit(f"{path} 里没有有效文案")
    return prompts


_SLUG_RE = re.compile(r"[^\w一-鿿-]+", re.UNICODE)


def slugify(text: str, limit: int = 40) -> str:
    s = _SLUG_RE.sub("-", text).strip("-")
    return (s[:limit] or "prompt").rstrip("-")


def validate_size(size: str) -> str:
    """5.0-lite：只接受小写 2k / 3k / 4k 或 WIDTHxHEIGHT（总像素 [3686400, 16777216]，宽高比 [1/16, 16]）。"""
    s = size.strip().lower()
    if s in ("1k", "1.5k"):
        raise SystemExit(
            f"size={size!r} 不可用：doubao-seedream-5.0-lite 不支持 1K（服务端实测 400 "
            "\"size must be one of 'WIDTHxHEIGHT', '2k', '3k', or '4k'\"）。\n"
            "  想要 1K 产物请用 --size 2k --downscale 1024（生成 2048x2048 后本地缩放，AFP 仍按 99/张计）。"
        )
    if s in ("2k", "3k", "4k"):
        return s
    m = re.fullmatch(r"(\d+)x(\d+)", s)
    if not m:
        raise SystemExit(f"size={size!r} 格式不对：用 2k / 3k / 4k 或 WIDTHxHEIGHT（如 2560x1440）")
    w, h = int(m.group(1)), int(m.group(2))
    px = w * h
    if not (IMAGE_MIN_PIXELS <= px <= IMAGE_MAX_PIXELS):
        raise SystemExit(
            f"size={size!r} 总像素 {px} 超出 5.0-lite 允许区间 [{IMAGE_MIN_PIXELS}, {IMAGE_MAX_PIXELS}]"
            "（最小 2560x1440，最大 4096x4096）"
        )
    ratio = w / h
    if not (1 / 16 <= ratio <= 16):
        raise SystemExit(f"size={size!r} 宽高比 {ratio:.3f} 超出 [1/16, 16]")
    return f"{w}x{h}"


def download(url: str, dest: Path, timeout: int = 180) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
    tmp.replace(dest)


def downscale_inplace(path: Path, target_long_edge: int) -> bool:
    """可选：本地把 2k 图缩到 1K 级别。需要 Pillow；没装就跳过并提示。"""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        log("  未安装 Pillow，跳过 --downscale（pip install pillow）")
        return False
    with Image.open(path) as im:
        w, h = im.size
        long_edge = max(w, h)
        if long_edge <= target_long_edge:
            return False
        scale = target_long_edge / long_edge
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        im = im.convert("RGBA") if path.suffix.lower() == ".png" else im.convert("RGB")
        im.resize(new_size, Image.LANCZOS).save(path)
    return True


def file_to_data_uri(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    fmt = {"jpg": "jpeg"}.get(ext, ext)  # data:image/<小写格式>;base64,...
    return f"data:image/{fmt};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# ----------------------------------------------------------------------------
# 图片生成
# ----------------------------------------------------------------------------
@dataclass
class ImageResult:
    index: int
    prompt: str
    file: str
    url: str
    size: str
    output_tokens: int
    afp: int
    created: int
    model: str


def generate_image(client: ArkPlanClient, index: int, prompt: str, out_dir: Path, args: argparse.Namespace) -> ImageResult:
    body = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "size": args.size,
        "response_format": "url",          # url 为 24h 有效的 TOS 签名链接，拿到立刻下载
        "output_format": args.format,      # png / jpeg
        "watermark": args.watermark,       # 默认 true 会加"AI 生成"水印，生产一般显式 false
        "sequential_image_generation": "disabled",  # 只出 1 张，避免模型自行出组图多扣 AFP
        "stream": False,
    }
    resp = client.request("POST", "/images/generations", body, timeout=HTTP_TIMEOUT_IMAGE)

    data = resp.get("data") or []
    if not data:
        err = resp.get("error") or {}
        raise ArkError(200, str(err.get("code") or "NoImage"), str(err.get("message") or "response has no data[]"), body=resp)
    item = data[0]
    if item.get("error"):
        # 单张审核失败等：出现在 data[i].error（组图口径）；单图场景多在顶层 error，这里两种都兜住
        e = item["error"]
        raise ArkError(200, str(e.get("code") or "ImageFailed"), str(e.get("message") or ""), body=resp)
    url = item.get("url")
    if not url:
        raise ArkError(200, "NoURL", "data[0] has no url", body=resp)

    dest = out_dir / f"{index:03d}-{slugify(prompt)}.{ 'jpg' if args.format == 'jpeg' else args.format }"
    download(url, dest)
    if args.downscale:
        downscale_inplace(dest, args.downscale)

    usage = resp.get("usage") or {}
    return ImageResult(
        index=index,
        prompt=prompt,
        file=str(dest),
        url=url,
        size=str(item.get("size") or args.size),
        output_tokens=int(usage.get("output_tokens") or 0),
        afp=IMAGE_AFP_PER_IMAGE * int(usage.get("generated_images") or 1),
        created=int(resp.get("created") or time.time()),
        model=str(resp.get("model") or IMAGE_MODEL),
    )


def run_images(client: ArkPlanClient, prompts: list[str], out_dir: Path, args: argparse.Namespace) -> list[ImageResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    done: dict[int, ImageResult] = {}
    if manifest_path.exists() and not args.force:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("kind") == "image" and Path(rec["file"]).exists():
                done[rec["index"]] = ImageResult(**{k: rec[k] for k in ImageResult.__dataclass_fields__})

    todo = [(i, p) for i, p in enumerate(prompts, start=1) if i not in done or done[i].prompt != p]
    if done:
        log(f"manifest 里已有 {len(done)} 张，跳过；剩余 {len(todo)} 张（--force 可全部重做）")

    results: dict[int, ImageResult] = dict(done)
    stop_reason: Optional[str] = None

    def worker(i: int, p: str) -> ImageResult:
        log(f"[{i:03d}] 生图: {p[:60]}")
        return generate_image(client, i, p, out_dir, args)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool, manifest_path.open("a", encoding="utf-8") as mf:
        futures = {pool.submit(worker, i, p): (i, p) for i, p in todo}
        for fut in as_completed(futures):
            i, p = futures[fut]
            try:
                r = fut.result()
            except ArkError as e:
                if e.is_plan_quota_exhausted:
                    stop_reason = f"套餐额度耗尽（{e.message.strip()}）。图片模型不支持超额后付费，只能等刷新。"
                    for f in futures:
                        f.cancel()
                    log(f"[{i:03d}] 失败: {e}")
                    continue
                log(f"[{i:03d}] 失败: {e}")
                mf.write(json.dumps({"kind": "image_error", "index": i, "prompt": p, "code": e.code, "message": e.message}, ensure_ascii=False) + "\n")
                mf.flush()
                continue
            except Exception as e:  # 下载失败等
                log(f"[{i:03d}] 失败: {type(e).__name__}: {e}")
                continue
            results[i] = r
            mf.write(json.dumps({"kind": "image", **asdict(r)}, ensure_ascii=False) + "\n")
            mf.flush()
            log(f"[{i:03d}] 完成 -> {r.file}  ({r.size}, {r.afp} AFP)")

    if stop_reason:
        log(f"\n!! 已停止: {stop_reason}")
    return [results[k] for k in sorted(results)]


# ----------------------------------------------------------------------------
# 视频生成（异步任务：创建 -> 轮询 -> 下载）
# ----------------------------------------------------------------------------
def estimate_video_afp(model: str, resolution: str, duration: int) -> Optional[float]:
    coef = VIDEO_AFP_PER_10K_TOKENS.get(model)
    wh = RESOLUTION_PIXELS.get(resolution)
    if coef is None or wh is None:
        return None
    tokens = duration * wh[0] * wh[1] * 24 / 1024   # 文档估算公式，帧率固定 24；准确值以 usage.completion_tokens 为准
    return tokens / 10_000 * coef


def submit_video(client: ArkPlanClient, image_source: str, prompt: str, args: argparse.Namespace) -> str:
    body = {
        "model": args.video_model,
        "content": [
            {"type": "text", "text": prompt},
            # 单张首帧图 role 可不填；这里显式写 first_frame 表示"图生视频"而非"参考图"
            {"type": "image_url", "image_url": {"url": image_source}, "role": "first_frame"},
        ],
        "resolution": args.video_resolution,
        "ratio": "adaptive",              # 跟随首帧图的宽高比，避免居中裁剪
        "duration": args.video_duration,  # 2.0 系列 4–15 秒
        "generate_audio": args.video_audio,
        "watermark": args.watermark,
        "return_last_frame": False,
    }
    resp = client.request("POST", "/contents/generations/tasks", body)
    task_id = resp.get("id")
    if not task_id:
        raise ArkError(200, "NoTaskId", "create task returned no id", body=resp)
    return str(task_id)


def wait_video(client: ArkPlanClient, task_id: str, interval: int = VIDEO_POLL_INTERVAL, max_wait: int = VIDEO_MAX_WAIT) -> dict:
    deadline = time.time() + max_wait
    last_status = None
    while time.time() < deadline:
        t = client.request("GET", f"/contents/generations/tasks/{task_id}")
        status = t.get("status")
        if status != last_status:
            log(f"  任务 {task_id}: {status}")
            last_status = status
        if status == "succeeded":
            return t
        if status in ("failed", "cancelled", "expired"):
            err = t.get("error") or {}
            raise ArkError(200, str(err.get("code") or status), str(err.get("message") or f"task {status}"), body=t)
        time.sleep(interval)
    raise TimeoutError(f"视频任务 {task_id} 在 {max_wait}s 内未完成，可稍后用 GET /contents/generations/tasks/{task_id} 再查（记录保留 7 天）")


def run_video(client: ArkPlanClient, image_path: Path, image_url: Optional[str], prompt: str, out_dir: Path, args: argparse.Namespace) -> Optional[Path]:
    est = estimate_video_afp(args.video_model, args.video_resolution, args.video_duration)
    est_txt = f"约 {est:,.0f} AFP" if est is not None else "AFP 未知"
    log(f"\n尝试图生视频: model={args.video_model} {args.video_resolution} {args.video_duration}s（{est_txt}，仅对成功任务计费）")

    # 同一次运行里刚拿到的 TOS URL（24h 有效）可直接喂给视频模型；重跑 / 只跑视频时改用本地文件 base64
    source = image_url or file_to_data_uri(image_path)

    try:
        task_id = submit_video(client, source, prompt, args)
    except ArkError as e:
        if e.is_unsupported_model:
            log(
                "  视频模型不可用（404 UnsupportedModel）。\n"
                "  这是 Agent Plan Small / Medium 套餐的预期行为：文档明确「Small、Medium 套餐仅供轻量化体验，不支持视频生成」，\n"
                "  Medium 档实测 doubao-seedance-2.0-mini 即返回此错误；服务端没有单独的“档位不够”错误码，文案与套餐外模型相同。\n"
                "  解决：升到 Large / Max（500 / 1000 元/月），或用方舟标准后付费 API（/api/v3 + 方舟 API Key + doubao-seedance-2-0-mini-260615）。\n"
                "  图片已全部生成完毕，本步骤跳过。"
            )
            return None
        if e.is_plan_quota_exhausted:
            log(f"  套餐额度耗尽，跳过视频：{e.message.strip()}")
            return None
        raise

    log(f"  任务已创建: {task_id}（记录保留 7 天，产物 URL 24 小时）")
    task = wait_video(client, task_id)
    video_url = (task.get("content") or {}).get("video_url")
    if not video_url:
        raise ArkError(200, "NoVideoURL", "task succeeded but content.video_url missing", body=task)

    dest = out_dir / f"video-{image_path.stem.split('-')[0]}.mp4"
    download(video_url, dest, timeout=600)
    usage = task.get("usage") or {}
    tokens = int(usage.get("completion_tokens") or 0)
    coef = VIDEO_AFP_PER_10K_TOKENS.get(args.video_model)
    afp_txt = f"{tokens / 10_000 * coef:,.0f} AFP" if coef else "AFP 未知"
    log(f"  视频完成 -> {dest}  (completion_tokens={tokens}, {afp_txt})")

    with (out_dir / "manifest.jsonl").open("a", encoding="utf-8") as mf:
        mf.write(json.dumps({
            "kind": "video", "task_id": task_id, "file": str(dest), "url": video_url,
            "model": task.get("model"), "resolution": task.get("resolution"), "duration": task.get("duration"),
            "completion_tokens": tokens, "source_image": str(image_path), "prompt": prompt,
        }, ensure_ascii=False) + "\n")
    return dest


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompts", default="prompts.txt", help="文案文件，每行一条（默认 prompts.txt）")
    ap.add_argument("--out", default="out", help="输出目录（默认 out/）")
    ap.add_argument("--base-url", default=os.environ.get("ARK_AGENT_PLAN_BASE_URL", PLAN_BASE_URL), help=argparse.SUPPRESS)
    ap.add_argument("--tier", default="medium", choices=sorted(PLAN_TIER_MONTHLY_AFP), help="你的 Agent Plan 档位，仅用于额度估算与提示（默认 medium）")

    g = ap.add_argument_group("图片")
    g.add_argument("--size", default=IMAGE_SIZE_DEFAULT, help="2k / 3k / 4k 或 WIDTHxHEIGHT；5.0-lite 不支持 1K（默认 2k = 2048x2048）")
    g.add_argument("--downscale", type=int, default=None, metavar="PX", help="下载后本地把长边缩到 PX（如 1024 得到 1K 产物；需 Pillow）")
    g.add_argument("--format", default="png", choices=["png", "jpeg"], help="output_format（默认 png）")
    g.add_argument("--watermark", action="store_true", help="保留「AI 生成」水印（默认关闭）")
    g.add_argument("--concurrency", type=int, default=2, help="并发张数（默认 2；IPM 上限 500，别开太大）")
    g.add_argument("--force", action="store_true", help="忽略 manifest，全部重新生成")

    v = ap.add_argument_group("视频（仅 Large / Max 套餐可用，Medium 会被 404 拒绝并自动跳过）")
    v.add_argument("--skip-video", action="store_true", help="不尝试视频")
    v.add_argument("--video-only", action="store_true", help="跳过生图，只做视频（配合 --video-from）")
    v.add_argument("--video-from", default=None, help="用这张本地图片做视频（默认取本次第一张图）")
    v.add_argument("--video-model", default=VIDEO_MODEL_DEFAULT, help=f"默认 {VIDEO_MODEL_DEFAULT}；可选 doubao-seedance-2.0 / -fast / -mini")
    v.add_argument("--video-resolution", default=VIDEO_RESOLUTION_DEFAULT, choices=["480p", "720p", "1080p", "4k"], help="-fast/-mini 仅 480p/720p（默认 720p）")
    v.add_argument("--video-duration", type=int, default=VIDEO_DURATION_DEFAULT, help="秒，2.0 系列 4–15（默认 5）")
    v.add_argument("--video-prompt", default=None, help="视频运镜文案（默认用第一张图的文案）")
    v.add_argument("--video-audio", action="store_true", help="生成同步音频（2.0 系列 AFP 不区分有声无声）")

    ap.add_argument("--dry-run", action="store_true", help="只解析文案并估算 AFP，不发请求")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    args.size = validate_size(args.size)
    if args.video_model in ("doubao-seedance-2.0-fast", "doubao-seedance-2.0-mini") and args.video_resolution not in ("480p", "720p"):
        raise SystemExit(f"{args.video_model} 只支持 480p / 720p")
    if not (4 <= args.video_duration <= 15):
        raise SystemExit("--video-duration 需在 4–15 秒之间（2.0 系列）")

    out_dir = Path(args.out)
    prompts = [] if args.video_only else load_prompts(Path(args.prompts))

    # ---- 额度估算 ----
    monthly = PLAN_TIER_MONTHLY_AFP[args.tier]
    daily_visual = monthly // 2
    img_afp = len(prompts) * IMAGE_AFP_PER_IMAGE
    vid_afp = None if args.skip_video else estimate_video_afp(args.video_model, args.video_resolution, args.video_duration)
    log(f"套餐 {args.tier}：月额度 {monthly:,} AFP，图片/视频日额度 {daily_visual:,} AFP（不受 5 小时 / 周限额）")
    log(f"待生成 {len(prompts)} 张 {IMAGE_MODEL} @ {args.size} = {img_afp:,} AFP（99 AFP/张，与像素无关）")
    if not args.skip_video:
        if args.tier in ("small", "medium"):
            log(f"视频：{args.tier} 档不支持视频生成，脚本仍会探测一次，预期 404 UnsupportedModel 后自动跳过（不扣 AFP）")
        elif vid_afp is not None:
            log(f"视频：{args.video_model} {args.video_resolution} {args.video_duration}s 估算 {vid_afp:,.0f} AFP")
    if img_afp > daily_visual:
        log(f"!! 图片总消耗 {img_afp:,} 超过日额度 {daily_visual:,}，图片模型不支持超额后付费，超出部分会 429 QuotaExceeded")
    if args.dry_run:
        log("--dry-run，未发请求")
        return 0

    api_key = os.environ.get(KEY_ENV)
    if not api_key:
        raise SystemExit(
            f"缺少环境变量 {KEY_ENV}。这是 Agent Plan 专属 API Key（控制台 → Agent Plan → 配置专属 API Key），\n"
            "不是「API Key 管理」里的方舟 API Key——两把 Key 互不通用，拿错了会 401 AuthenticationError。"
        )
    client = ArkPlanClient(api_key, base_url=args.base_url)

    # ---- 图片 ----
    results: list[ImageResult] = []
    if not args.video_only:
        results = run_images(client, prompts, out_dir, args)
        ok = len(results)
        log(f"\n图片完成 {ok}/{len(prompts)} 张，共 {ok * IMAGE_AFP_PER_IMAGE:,} AFP；清单 {out_dir / 'manifest.jsonl'}")
        if ok == 0:
            return 1

    if args.skip_video:
        return 0

    # ---- 视频：第一张图 ----
    if args.video_from:
        first_path = Path(args.video_from)
        if not first_path.is_file():
            raise SystemExit(f"--video-from 文件不存在: {first_path}")
        first_url = None
        prompt = args.video_prompt or first_path.stem
    else:
        if not results:
            raise SystemExit("--video-only 需要配合 --video-from 指定图片")
        first = results[0]
        first_path, first_url = Path(first.file), first.url
        # 本地做过缩放时，远端 URL 仍是原 2k 图；两者宽高比一致，用 URL 更省请求体
        prompt = args.video_prompt or first.prompt

    try:
        run_video(client, first_path, first_url, prompt, out_dir, args)
    except ArkError as e:
        log(f"视频失败: {e}")
        return 2
    except TimeoutError as e:
        log(str(e))
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断")
        sys.exit(130)
