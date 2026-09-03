#!/usr/bin/env python3
"""
image_to_video.py
==================

内容生成小工具：
  1. 用智谱 GLM-Image 模型（`POST /paas/v4/images/generations`，同步接口）根据一段
     文字描述生成一张图片；
  2. 把这张图片的 URL 作为首帧，用 CogVideoX-3 模型（`POST /paas/v4/videos/generations`，
     只有异步接口）生成一段视频；
  3. 视频生成是异步任务，轮询通用异步结果接口
     `GET /paas/v4/async-result/{id}` 直到 `task_status` 变为 `SUCCESS`/`FAIL`；
  4. 把生成的图片和视频下载到本地。

依赖：
    pip install requests

用法示例：
    export ZHIPUAI_API_KEY="你的 API Key"
    python image_to_video.py \
        --image-prompt "一只柯基犬在樱花树下奔跑，阳光透过花瓣，插画风格" \
        --video-prompt "镜头缓慢推近，樱花花瓣随风飘落，柯基犬转头看向镜头" \
        --output-dir ./output

参考资料：Skillify `bigmodel-cn` 技能包
  - references/media.md（图像生成 / 视频生成 / 异步轮询）
  - references/models.md（模型选型）
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

# Base URL 固定为 https://open.bigmodel.cn/api/，所有接口路径拼在它后面。
BASE_URL = "https://open.bigmodel.cn/api"

IMAGE_GENERATIONS_PATH = "/paas/v4/images/generations"
VIDEO_GENERATIONS_PATH = "/paas/v4/videos/generations"
ASYNC_RESULT_PATH = "/paas/v4/async-result/{task_id}"

# API Key 通过环境变量读取，绝不要硬编码进代码。
# 从控制台获取：https://bigmodel.cn/usercenter/proj-mgmt/apikeys
API_KEY_ENV_VAR = "ZHIPUAI_API_KEY"

DEFAULT_TIMEOUT_SECONDS = 60  # 单次 HTTP 请求超时（提交任务用，不是轮询超时）


# --------------------------------------------------------------------------
# 异常 & 数据结构
# --------------------------------------------------------------------------


class BigModelAPIError(RuntimeError):
    """智谱开放平台接口返回错误时抛出。"""


@dataclasses.dataclass
class ImageResult:
    url: str


@dataclasses.dataclass
class VideoResult:
    url: str
    cover_image_url: Optional[str] = None


# --------------------------------------------------------------------------
# 基础工具函数
# --------------------------------------------------------------------------


def _get_api_key() -> str:
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"未找到 API Key，请先设置环境变量 {API_KEY_ENV_VAR}，"
            f"例如：export {API_KEY_ENV_VAR}=your_api_key_here"
        )
    return api_key


def _headers() -> dict[str, str]:
    # 鉴权统一是 HTTP Bearer：Authorization: Bearer <API_KEY>
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    resp = requests.post(
        url, headers=_headers(), json=payload, timeout=DEFAULT_TIMEOUT_SECONDS
    )
    return _parse_response(resp, url)


def _get_json(path: str) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=_headers(), timeout=DEFAULT_TIMEOUT_SECONDS)
    return _parse_response(resp, url)


def _parse_response(resp: requests.Response, url: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise BigModelAPIError(f"请求 {url} 返回了非 JSON 响应：{resp.text[:500]}")

    if not resp.ok:
        # 智谱错误响应一般形如 {"error": {"code": "...", "message": "..."}}
        err = data.get("error") if isinstance(data, dict) else None
        message = err.get("message") if isinstance(err, dict) else data
        raise BigModelAPIError(
            f"请求 {url} 失败，HTTP {resp.status_code}：{message}"
        )
    return data


def _download_file(url: str, dest_path: str) -> None:
    """下载图片/视频结果文件到本地（结果 URL 一般是有有效期的临时链接，需及时转存）。"""
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _filename_from_url(url: str, fallback: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    return name if name else fallback


# --------------------------------------------------------------------------
# 第一步：GLM-Image 文生图（同步接口）
# --------------------------------------------------------------------------


def generate_image(
    prompt: str,
    size: str = "1728x960",
    quality: str = "hd",
    watermark_enabled: bool = True,
) -> ImageResult:
    """
    调用 GLM-Image 同步文生图接口：POST /paas/v4/images/generations

    注意：
      - `model` 固定传 "glm-image"。
      - `glm-image` 仅支持 quality="hd"（耗时约 20 秒），这是同步阻塞调用。
      - 返回的图片 URL 是临时链接，有效期 30 天，本脚本会立即下载转存到本地。
    """
    payload = {
        "model": "glm-image",
        "prompt": prompt,
        "quality": quality,
        "size": size,
        "watermark_enabled": watermark_enabled,
    }
    data = _post_json(IMAGE_GENERATIONS_PATH, payload)

    images = data.get("data") or []
    if not images or "url" not in images[0]:
        raise BigModelAPIError(f"图像生成接口返回了意外的响应结构：{data}")

    return ImageResult(url=images[0]["url"])


# --------------------------------------------------------------------------
# 第二步：CogVideoX-3 图生视频（首帧驱动，异步接口）
# --------------------------------------------------------------------------


def create_video_task(
    first_frame_image_url: str,
    prompt: Optional[str] = None,
    model: str = "cogvideox-3",
    quality: str = "quality",
    size: str = "1920x1080",
    fps: int = 30,
    duration: int = 5,
    with_audio: bool = False,
    watermark_enabled: bool = True,
) -> str:
    """
    调用视频生成接口提交任务：POST /paas/v4/videos/generations

    首帧图片的传法：`image_url` 传一个单独的字符串（图片 URL 或 Base64），
    CogVideoX-3 会把它当作视频的第一帧来生成后续画面。
    （如果要同时指定首帧 + 尾帧，则把 image_url 传成 [首帧URL, 尾帧URL] 的
    两元素数组；本脚本只做首帧驱动，所以传单个 URL 字符串。）

    该接口永远是异步的：提交后立即返回 {"id": ..., "task_status": "PROCESSING"}，
    真正的视频结果需要轮询 poll_async_result() 获取。
    """
    payload: dict[str, Any] = {
        "model": model,
        "image_url": first_frame_image_url,  # 单个 URL = 首帧驱动
        "quality": quality,
        "size": size,
        "fps": fps,
        "duration": duration,
        "with_audio": with_audio,
        "watermark_enabled": watermark_enabled,
    }
    if prompt:
        payload["prompt"] = prompt

    data = _post_json(VIDEO_GENERATIONS_PATH, payload)

    task_id = data.get("id")
    if not task_id:
        raise BigModelAPIError(f"视频生成任务提交后未返回任务 id：{data}")
    return task_id


# --------------------------------------------------------------------------
# 第三步：轮询通用异步结果接口
# --------------------------------------------------------------------------


def poll_async_result(
    task_id: str,
    interval_seconds: float = 5.0,
    timeout_seconds: float = 300.0,
    on_poll: Optional[Any] = None,
) -> dict[str, Any]:
    """
    轮询 GET /paas/v4/async-result/{id}，直到 task_status 变为 SUCCESS 或 FAIL。

    这是图像异步接口和视频生成接口共用的通用查询接口——本脚本里视频生成
    只有异步接口，所以必须走这条轮询逻辑。
    """
    path = ASYNC_RESULT_PATH.format(task_id=task_id)
    deadline = time.monotonic() + timeout_seconds

    while True:
        data = _get_json(path)
        status = data.get("task_status")

        if on_poll:
            on_poll(status, data)

        if status == "SUCCESS":
            return data
        if status == "FAIL":
            raise BigModelAPIError(f"任务 {task_id} 生成失败：{data}")

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"轮询任务 {task_id} 超时（{timeout_seconds} 秒），"
                f"最后一次状态：{status}"
            )
        time.sleep(interval_seconds)


def extract_video_result(async_result: dict[str, Any]) -> VideoResult:
    video_results = async_result.get("video_result") or []
    if not video_results or "url" not in video_results[0]:
        raise BigModelAPIError(f"异步结果里没有找到 video_result：{async_result}")
    first = video_results[0]
    return VideoResult(url=first["url"], cover_image_url=first.get("cover_image_url"))


# --------------------------------------------------------------------------
# 编排：文生图 -> 图生视频（首帧）-> 轮询 -> 下载
# --------------------------------------------------------------------------


def run_pipeline(
    image_prompt: str,
    video_prompt: Optional[str],
    output_dir: str,
    image_size: str = "1728x960",
    video_size: str = "1920x1080",
    video_model: str = "cogvideox-3",
    video_quality: str = "quality",
    fps: int = 30,
    duration: int = 5,
    with_audio: bool = False,
    watermark_enabled: bool = True,
    poll_interval: float = 5.0,
    poll_timeout: float = 300.0,
) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)

    # ---- 1. 文生图（GLM-Image，同步） ----
    print(f"[1/4] 调用 GLM-Image 生成图片，prompt: {image_prompt!r}")
    image_result = generate_image(prompt=image_prompt, size=image_size)
    print(f"      图片生成成功: {image_result.url}")

    image_local_path = os.path.join(
        output_dir, _filename_from_url(image_result.url, "first_frame.png")
    )
    _download_file(image_result.url, image_local_path)
    print(f"      已下载到本地: {image_local_path}")

    # ---- 2. 提交视频生成任务（CogVideoX-3，图生视频，首帧驱动，异步） ----
    print(
        f"[2/4] 提交 CogVideoX-3 视频生成任务，首帧图片: {image_result.url}"
        f"{'，动作描述: ' + video_prompt if video_prompt else ''}"
    )
    task_id = create_video_task(
        first_frame_image_url=image_result.url,
        prompt=video_prompt,
        model=video_model,
        quality=video_quality,
        size=video_size,
        fps=fps,
        duration=duration,
        with_audio=with_audio,
        watermark_enabled=watermark_enabled,
    )
    print(f"      任务已提交，task_id = {task_id}")

    # ---- 3. 轮询异步结果 ----
    print(f"[3/4] 轮询任务结果（每 {poll_interval} 秒一次，超时 {poll_timeout} 秒）...")

    def _on_poll(status: str, _data: dict[str, Any]) -> None:
        print(f"      当前状态: {status}")

    async_result = poll_async_result(
        task_id,
        interval_seconds=poll_interval,
        timeout_seconds=poll_timeout,
        on_poll=_on_poll,
    )
    video_result = extract_video_result(async_result)
    print(f"      视频生成成功: {video_result.url}")

    # ---- 4. 下载视频（及封面图） ----
    print("[4/4] 下载视频到本地...")
    video_local_path = os.path.join(
        output_dir, _filename_from_url(video_result.url, "output_video.mp4")
    )
    _download_file(video_result.url, video_local_path)
    print(f"      视频已下载到: {video_local_path}")

    if video_result.cover_image_url:
        cover_local_path = os.path.join(
            output_dir,
            _filename_from_url(video_result.cover_image_url, "cover.jpg"),
        )
        _download_file(video_result.cover_image_url, cover_local_path)
        print(f"      封面图已下载到: {cover_local_path}")

    return image_local_path, video_local_path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用 GLM-Image 生成首帧图片，再用 CogVideoX-3 生成首帧驱动的视频。"
    )
    parser.add_argument(
        "--image-prompt",
        required=True,
        help="文生图的文字描述，例如：'一只柯基犬在樱花树下奔跑，阳光透过花瓣，插画风格'",
    )
    parser.add_argument(
        "--video-prompt",
        default=None,
        help="视频的动作/运镜描述（可选），例如：'镜头缓慢推近，樱花花瓣随风飘落'",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="生成的图片和视频保存目录，默认 ./output",
    )
    parser.add_argument(
        "--image-size",
        default="1728x960",
        help="GLM-Image 输出尺寸，默认 1728x960（16:9 附近，便于和视频画幅接近）",
    )
    parser.add_argument(
        "--video-size",
        default="1920x1080",
        choices=[
            "1280x720",
            "720x1280",
            "1024x1024",
            "1920x1080",
            "1080x1920",
            "2048x1080",
            "3840x2160",
        ],
        help="CogVideoX-3 输出尺寸，默认 1920x1080",
    )
    parser.add_argument(
        "--video-model",
        default="cogvideox-3",
        help="视频生成模型，默认 cogvideox-3",
    )
    parser.add_argument(
        "--video-quality",
        default="quality",
        choices=["quality", "speed"],
        help="视频生成质量/速度偏好，默认 quality",
    )
    parser.add_argument(
        "--fps", type=int, default=30, choices=[30, 60], help="视频帧率，默认 30"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=5,
        choices=[5, 10],
        help="视频时长（秒），cogvideox-3 支持 5 或 10，默认 5",
    )
    parser.add_argument(
        "--with-audio", action="store_true", help="是否生成 AI 音效，默认不生成"
    )
    parser.add_argument(
        "--no-watermark",
        action="store_true",
        help="关闭水印（需要账号已在控制台签署去水印免责声明，否则接口会报错）",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=5.0, help="轮询间隔秒数，默认 5 秒"
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=300.0,
        help="轮询总超时秒数，默认 300 秒",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        image_path, video_path = run_pipeline(
            image_prompt=args.image_prompt,
            video_prompt=args.video_prompt,
            output_dir=args.output_dir,
            image_size=args.image_size,
            video_size=args.video_size,
            video_model=args.video_model,
            video_quality=args.video_quality,
            fps=args.fps,
            duration=args.duration,
            with_audio=args.with_audio,
            watermark_enabled=not args.no_watermark,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )
    except (BigModelAPIError, TimeoutError, RuntimeError) as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 1

    print("\n完成！")
    print(f"  首帧图片: {image_path}")
    print(f"  生成视频: {video_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
