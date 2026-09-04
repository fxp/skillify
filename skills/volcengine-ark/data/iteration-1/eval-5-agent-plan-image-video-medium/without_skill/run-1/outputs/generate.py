#!/usr/bin/env python3
"""
Batch text-to-image (+ optional image-to-video) on 火山方舟 (Volcengine Ark).

  * Reads one prompt per line from prompts.txt (blank lines and lines starting
    with '#' are ignored).
  * Generates one 1K image per prompt with Doubao Seedream and saves it to out/.
  * Optionally turns the FIRST generated image into a 5-second video with
    Doubao Seedance (async task API + polling) and saves out/video_001.mp4.

Auth / endpoints are read from environment variables so the same script works
against pay-as-you-go keys and against Agent Plan keys:

  ARK_API_KEY       required. Your Ark API key (Agent Plan key or normal key).
  ARK_BASE_URL      default https://ark.cn-beijing.volces.com/api/v3
  ARK_IMAGE_MODEL   default doubao-seedream-4-0-250828
  ARK_VIDEO_MODEL   default doubao-seedance-1-0-pro-250528

Usage:
  export ARK_API_KEY=...
  python generate.py                          # images + video (video is best-effort)
  python generate.py --no-video               # images only
  python generate.py --prompts my.txt --out out --workers 2
  python generate.py --video-only             # reuse out/001.jpg, only make the video

The script never calls the API without ARK_API_KEY set, is idempotent (existing
files are skipped), retries on 429/5xx, and records every result in
out/manifest.jsonl.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-4-0-250828"
DEFAULT_VIDEO_MODEL = "doubao-seedance-1-0-pro-250528"

IMAGE_SIZE_1K = "1K"                 # Seedream 4.x accepts "1K"/"2K"/"4K" or "WxH"
IMAGE_SIZE_1K_LEGACY = "1024x1024"   # Seedream 3.x only accepts explicit "WxH"
VIDEO_DURATION_S = 5
VIDEO_RESOLUTION = "720p"

HTTP_TIMEOUT_S = 120
MAX_RETRIES = 5
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 15 * 60

# Ark error codes that mean "retrying will not help for this prompt".
NON_RETRYABLE_CONTENT_CODES = {
    "SensitiveContentDetected",
    "InputTextSensitiveContentDetected",
    "InputImageSensitiveContentDetected",
    "OutputImageSensitiveContentDetected",
    "OutputVideoSensitiveContentDetected",
    "InvalidParameter",
}
# Ark error codes that mean "this key / plan cannot use this model at all".
ENTITLEMENT_CODES = {
    "ModelNotOpen",
    "ModelNotFound",
    "AccountOverdueError",
    "QuotaExceeded",
    "AccessDenied",
    "AuthenticationError",
    "InvalidEndpointOrModel",
}

log = logging.getLogger("ark-batch")


class ArkError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool):
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable

    @property
    def is_entitlement(self) -> bool:
        return self.code in ENTITLEMENT_CODES or self.status in (401, 403)


# --------------------------------------------------------------------------- #
# HTTP client
# --------------------------------------------------------------------------- #

class ArkClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        if not api_key:
            raise SystemExit("ARK_API_KEY is not set. export ARK_API_KEY=<your key> and retry.")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ark-batch-image-video/1.0",
        })

    # -- low level --------------------------------------------------------- #
    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self.base_url}{path}"
        delay = 2.0
        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=HTTP_TIMEOUT_S, **kwargs)
            except requests.RequestException as exc:  # network-level failure
                last_exc = exc
                log.warning("network error (%s), attempt %d/%d", exc, attempt, MAX_RETRIES)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue

            if resp.ok:
                return resp.json()

            code, message = _parse_error(resp)
            retryable = resp.status_code == 429 or resp.status_code >= 500
            err = ArkError(resp.status_code, code, message, retryable)
            if not retryable or attempt == MAX_RETRIES:
                raise err
            retry_after = resp.headers.get("Retry-After")
            sleep_s = float(retry_after) if retry_after and retry_after.isdigit() else delay
            log.warning("%s -> retrying in %.0fs (attempt %d/%d)", err, sleep_s, attempt, MAX_RETRIES)
            time.sleep(sleep_s)
            delay = min(delay * 2, 30)
        raise ArkError(0, "NetworkError", str(last_exc), retryable=False)

    # -- images ------------------------------------------------------------ #
    def generate_image(self, model: str, prompt: str, size: str) -> dict:
        body = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",   # one round-trip, no 24h URL expiry
            "watermark": False,
        }
        if "seedream-4" in model or "seedream-5" in model:
            # Seedream 4.x extras; harmless to omit for older models.
            body["sequential_image_generation"] = "disabled"
            body["stream"] = False
        return self._request("POST", "/images/generations", json=body)

    # -- video (async task API) ------------------------------------------- #
    def create_video_task(self, model: str, prompt: str, image_data_url: str,
                          duration: int, resolution: str) -> dict:
        # Seedance reads generation controls from the text as "--flag value".
        text = (
            f"{prompt} --resolution {resolution} --duration {duration} "
            f"--ratio adaptive --camerafixed false --watermark false"
        )
        body = {
            "model": model,
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_data_url}},  # first frame
            ],
        }
        return self._request("POST", "/contents/generations/tasks", json=body)

    def get_video_task(self, task_id: str) -> dict:
        return self._request("GET", f"/contents/generations/tasks/{task_id}")

    def download(self, url: str, dest: Path) -> None:
        with self.session.get(url, stream=True, timeout=HTTP_TIMEOUT_S, headers={"Authorization": None}) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
            tmp.replace(dest)


def _parse_error(resp: requests.Response) -> tuple[str, str]:
    try:
        err = resp.json().get("error", {})
        return str(err.get("code", resp.status_code)), str(err.get("message", resp.text[:300]))
    except ValueError:
        return str(resp.status_code), resp.text[:300]


# --------------------------------------------------------------------------- #
# Work
# --------------------------------------------------------------------------- #

@dataclass
class ImageResult:
    index: int
    prompt: str
    file: Optional[str]
    model: str
    size_requested: str
    size_actual: Optional[str] = None
    status: str = "ok"
    error: Optional[str] = None
    usage: Optional[dict] = None


def read_prompts(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"prompts file not found: {path}")
    prompts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            prompts.append(line)
    if not prompts:
        raise SystemExit(f"no prompts found in {path}")
    return prompts


def image_size_for(model: str) -> str:
    return IMAGE_SIZE_1K_LEGACY if "seedream-3" in model else IMAGE_SIZE_1K


def generate_one(client: ArkClient, model: str, index: int, prompt: str, out_dir: Path) -> ImageResult:
    dest = out_dir / f"{index:03d}.jpg"
    size = image_size_for(model)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("[%03d] exists, skipping", index)
        return ImageResult(index, prompt, str(dest), model, size, status="skipped")

    try:
        resp = client.generate_image(model, prompt, size)
    except ArkError as e:
        if e.is_entitlement:
            raise  # stop the whole run: the key/plan cannot use this model
        log.error("[%03d] failed: %s", index, e)
        return ImageResult(index, prompt, None, model, size, status="failed", error=str(e))

    data = (resp.get("data") or [{}])[0]
    if "b64_json" in data:
        dest.write_bytes(base64.b64decode(data["b64_json"]))
    elif "url" in data:
        client.download(data["url"], dest)
    else:
        err = data.get("error") or resp.get("error") or {"message": "empty response"}
        log.error("[%03d] no image returned: %s", index, err)
        return ImageResult(index, prompt, None, model, size, status="failed", error=json.dumps(err, ensure_ascii=False))

    log.info("[%03d] saved %s (%s)", index, dest.name, data.get("size", size))
    return ImageResult(index, prompt, str(dest), model, size, size_actual=data.get("size"), usage=resp.get("usage"))


def make_video(client: ArkClient, model: str, prompt: str, image_path: Path, dest: Path) -> dict:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("video exists, skipping: %s", dest)
        return {"status": "skipped", "file": str(dest)}

    b64 = base64.b64encode(image_path.read_bytes()).decode()
    data_url = f"data:image/jpeg;base64,{b64}"

    task = client.create_video_task(model, prompt, data_url, VIDEO_DURATION_S, VIDEO_RESOLUTION)
    task_id = task["id"]
    log.info("video task created: %s (model=%s)", task_id, model)

    deadline = time.monotonic() + POLL_TIMEOUT_S
    while True:
        info = client.get_video_task(task_id)
        status = info.get("status")
        if status == "succeeded":
            url = info["content"]["video_url"]
            client.download(url, dest)
            log.info("video saved %s", dest)
            return {"status": "ok", "file": str(dest), "task_id": task_id, "usage": info.get("usage")}
        if status in ("failed", "cancelled", "expired"):
            err = info.get("error") or {}
            msg = f"video task {task_id} {status}: {err.get('code')} {err.get('message')}"
            log.error(msg)
            return {"status": "failed", "task_id": task_id, "error": msg}
        if time.monotonic() > deadline:
            return {"status": "failed", "task_id": task_id, "error": "poll timeout"}
        log.info("video task %s: %s ... waiting %ss", task_id, status, POLL_INTERVAL_S)
        time.sleep(POLL_INTERVAL_S)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prompts", default="prompts.txt", type=Path)
    p.add_argument("--out", default="out", type=Path)
    p.add_argument("--workers", type=int, default=1,
                   help="parallel image requests (keep low: plan keys have RPM limits)")
    p.add_argument("--image-model", default=os.getenv("ARK_IMAGE_MODEL", DEFAULT_IMAGE_MODEL))
    p.add_argument("--video-model", default=os.getenv("ARK_VIDEO_MODEL", DEFAULT_VIDEO_MODEL))
    g = p.add_mutually_exclusive_group()
    g.add_argument("--no-video", action="store_true", help="only generate images")
    g.add_argument("--video-only", action="store_true", help="skip images, animate existing out/001.jpg")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    client = ArkClient(os.getenv("ARK_API_KEY", ""), os.getenv("ARK_BASE_URL", DEFAULT_BASE_URL))
    prompts = read_prompts(args.prompts)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.jsonl"

    results: list[ImageResult] = []
    if not args.video_only:
        log.info("generating %d image(s) with %s, size=%s", len(prompts), args.image_model,
                 image_size_for(args.image_model))
        try:
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                futs = [pool.submit(generate_one, client, args.image_model, i, pr, args.out)
                        for i, pr in enumerate(prompts, start=1)]
                for f in as_completed(futs):
                    results.append(f.result())
        except ArkError as e:
            log.error("aborting: %s", e)
            log.error("This key/plan cannot call model %r. See NOTES.md -> 'Plan tier'.", args.image_model)
            _write_manifest(manifest, results)
            return 2
        results.sort(key=lambda r: r.index)
        _write_manifest(manifest, results)
        ok = sum(r.status in ("ok", "skipped") for r in results)
        log.info("images done: %d/%d ok", ok, len(results))

    if args.no_video:
        return 0

    first = args.out / "001.jpg"
    if not first.exists():
        log.error("no first image at %s; cannot make video", first)
        return 1

    try:
        vres = make_video(client, args.video_model, prompts[0], first, args.out / "video_001.mp4")
    except ArkError as e:
        if e.is_entitlement:
            log.warning("video model %r is not available on this key/plan (%s). "
                        "Images are done; video skipped.", args.video_model, e)
            vres = {"status": "unavailable", "error": str(e)}
        else:
            log.error("video failed: %s", e)
            vres = {"status": "failed", "error": str(e)}
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "video", "prompt": prompts[0], "model": args.video_model, **vres},
                            ensure_ascii=False) + "\n")
    return 0 if vres["status"] in ("ok", "skipped", "unavailable") else 1


def _write_manifest(path: Path, results: list[ImageResult]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in sorted(results, key=lambda r: r.index):
            fh.write(json.dumps({"type": "image", **asdict(r)}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
