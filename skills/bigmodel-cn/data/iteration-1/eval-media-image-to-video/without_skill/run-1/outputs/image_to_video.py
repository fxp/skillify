#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
image_to_video.py
==================

一个基于智谱开放平台（bigmodel.cn）的"文字 -> 图片 -> 视频"内容生成小工具。

流程：
  1. 调用 GLM-Image 模型，根据文字描述生成一张图片（同步接口，直接返回图片 URL）。
  2. 将第 1 步生成的图片作为首帧图，调用 CogVideoX-3 模型生成一段视频。
     视频生成是异步任务：提交后立即返回一个 task_id，需要轮询结果接口，
     直到任务状态变为 SUCCESS / FAIL。
  3. 将生成的图片和视频下载到本地。

使用前准备：
  1. 安装依赖：
       pip install requests
  2. 设置环境变量 ZHIPUAI_API_KEY 为你在 bigmodel.cn 控制台申请的 API Key：
       export ZHIPUAI_API_KEY="your_real_api_key_here"

用法示例：
  python image_to_video.py --prompt "一只橘猫在雪地里奔跑，电影感，4K" \
      --out-dir ./outputs

注意：
  - 本脚本未内置真实 API Key，需要通过环境变量注入，避免把密钥硬编码到代码里。
  - 智谱开放平台的接口字段/路径可能随版本更新而调整，使用前建议对照官方文档
    （https://open.bigmodel.cn/dev/api）核对最新的请求/响应格式。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

# 智谱开放平台的 API Key，从环境变量读取，避免明文写在代码中。
# 未设置时使用占位符，脚本会在真正发起请求前给出明确报错，方便定位问题。
API_KEY = os.environ.get("ZHIPUAI_API_KEY", "YOUR_API_KEY_HERE")

# API 根地址（v4）。
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

# 具体接口路径。
IMAGE_GENERATIONS_URL = f"{BASE_URL}/images/generations"
VIDEO_GENERATIONS_URL = f"{BASE_URL}/videos/generations"
ASYNC_RESULT_URL = f"{BASE_URL}/async-result/{{task_id}}"

# 模型名称。
IMAGE_MODEL = "glm-image"
VIDEO_MODEL = "cogvideox-3"

# 轮询参数。
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600  # 视频生成通常需要几十秒到几分钟，超时时间放宽一些。

# HTTP 请求超时（连接超时, 读超时）。
REQUEST_TIMEOUT = (10, 60)


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass
class ImageResult:
    url: str
    raw_response: dict[str, Any]


@dataclass
class VideoResult:
    video_url: str
    cover_image_url: Optional[str]
    raw_response: dict[str, Any]


class BigModelAPIError(RuntimeError):
    """封装智谱开放平台返回的错误信息，便于上层统一处理。"""


# --------------------------------------------------------------------------
# 基础工具函数
# --------------------------------------------------------------------------


def _auth_headers() -> dict[str, str]:
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        raise BigModelAPIError(
            "未检测到有效的 API Key。请先执行："
            "\n    export ZHIPUAI_API_KEY=\"你的真实API Key\""
            "\n然后再运行本脚本。"
        )
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _raise_for_api_error(resp: requests.Response) -> dict[str, Any]:
    """统一处理 HTTP 层与业务层的错误。"""
    try:
        data = resp.json()
    except ValueError as exc:
        raise BigModelAPIError(
            f"响应不是合法的 JSON（HTTP {resp.status_code}）：{resp.text[:500]}"
        ) from exc

    if not resp.ok:
        err = data.get("error", data)
        raise BigModelAPIError(
            f"接口调用失败（HTTP {resp.status_code}）：{err}"
        )

    # 智谱部分接口即使 HTTP 200，也可能在 body 里携带 error 字段。
    if isinstance(data, dict) and data.get("error"):
        raise BigModelAPIError(f"接口返回业务错误：{data['error']}")

    return data


def download_file(url: str, dest_path: Path) -> Path:
    """下载远程文件到本地路径，返回本地路径。"""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
    return dest_path


# --------------------------------------------------------------------------
# 第一步：GLM-Image 文生图（同步接口）
# --------------------------------------------------------------------------


def generate_image(
    prompt: str,
    size: str = "1024x1024",
) -> ImageResult:
    """
    调用 GLM-Image 模型，根据文字描述生成一张图片。

    该接口是同步的：请求发出后直接返回结果，不需要轮询。

    Args:
        prompt: 图片内容的文字描述。
        size: 生成图片的分辨率，如 "1024x1024"。

    Returns:
        ImageResult，其中 url 为生成图片的可下载地址。
    """
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
    }

    resp = requests.post(
        IMAGE_GENERATIONS_URL,
        headers=_auth_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    data = _raise_for_api_error(resp)

    images = data.get("data") or []
    if not images or "url" not in images[0]:
        raise BigModelAPIError(f"图片生成接口返回了非预期的结构：{data}")

    return ImageResult(url=images[0]["url"], raw_response=data)


# --------------------------------------------------------------------------
# 第二步：CogVideoX-3 图生视频（异步接口 + 轮询）
# --------------------------------------------------------------------------


def create_video_task(
    prompt: str,
    first_frame_image_url: str,
    quality: str = "speed",
    with_audio: bool = False,
    size: str = "1920x1080",
    fps: int = 30,
) -> str:
    """
    提交一个"以给定图片为首帧，结合文字描述生成视频"的异步任务。

    Args:
        prompt: 视频内容/运镜/风格的文字描述。
        first_frame_image_url: 作为视频首帧的图片 URL（这里直接复用
            GLM-Image 返回的图片 URL；也可以传本地图片的 base64）。
        quality: "speed"（速度优先）或 "quality"（质量优先）。
        with_audio: 是否让模型同时生成配套音效/配音。
        size: 输出视频分辨率。
        fps: 输出视频帧率。

    Returns:
        task_id：用于后续轮询任务状态的任务 ID。
    """
    payload = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        # image_url 字段用于传入首帧图片，实现"图生视频"。
        "image_url": first_frame_image_url,
        "quality": quality,
        "with_audio": with_audio,
        "size": size,
        "fps": fps,
    }

    resp = requests.post(
        VIDEO_GENERATIONS_URL,
        headers=_auth_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    data = _raise_for_api_error(resp)

    task_id = data.get("id")
    if not task_id:
        raise BigModelAPIError(f"视频生成任务提交后未返回 task id：{data}")

    return task_id


def poll_video_task(
    task_id: str,
    interval_seconds: int = POLL_INTERVAL_SECONDS,
    timeout_seconds: int = POLL_TIMEOUT_SECONDS,
) -> VideoResult:
    """
    轮询异步视频生成任务，直到任务完成（成功/失败）或超时。

    智谱异步任务的典型状态取值："PROCESSING" -> "SUCCESS" / "FAIL"。
    """
    url = ASYNC_RESULT_URL.format(task_id=task_id)
    deadline = time.monotonic() + timeout_seconds

    while True:
        resp = requests.get(url, headers=_auth_headers(), timeout=REQUEST_TIMEOUT)
        data = _raise_for_api_error(resp)

        status = data.get("task_status")
        print(f"[轮询] task_id={task_id} 状态={status}")

        if status == "SUCCESS":
            results = data.get("video_result") or []
            if not results or "url" not in results[0]:
                raise BigModelAPIError(f"任务成功但未返回视频地址：{data}")
            return VideoResult(
                video_url=results[0]["url"],
                cover_image_url=results[0].get("cover_image_url"),
                raw_response=data,
            )

        if status == "FAIL":
            raise BigModelAPIError(f"视频生成任务失败：{data}")

        # 仍在处理中（PROCESSING 或其他中间状态），继续等待。
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"轮询超时（{timeout_seconds}s），task_id={task_id} 仍未完成。"
            )

        time.sleep(interval_seconds)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def run(
    prompt: str,
    video_prompt: Optional[str],
    out_dir: Path,
    image_size: str = "1024x1024",
    video_size: str = "1920x1080",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    print(f"[1/4] 调用 {IMAGE_MODEL} 生成首帧图片……")
    print(f"      提示词：{prompt}")
    image_result = generate_image(prompt=prompt, size=image_size)
    print(f"      生成成功，图片 URL：{image_result.url}")

    image_path = out_dir / f"first_frame_{timestamp}.png"
    print(f"[2/4] 下载图片到本地：{image_path}")
    download_file(image_result.url, image_path)

    print(f"[3/4] 调用 {VIDEO_MODEL} 提交图生视频任务……")
    effective_video_prompt = video_prompt or prompt
    task_id = create_video_task(
        prompt=effective_video_prompt,
        first_frame_image_url=image_result.url,
        size=video_size,
    )
    print(f"      任务已提交，task_id={task_id}，开始轮询……")

    video_result = poll_video_task(task_id)
    print(f"      视频生成成功，视频 URL：{video_result.video_url}")

    video_path = out_dir / f"video_{timestamp}.mp4"
    print(f"[4/4] 下载视频到本地：{video_path}")
    download_file(video_result.video_url, video_path)

    if video_result.cover_image_url:
        cover_path = out_dir / f"video_cover_{timestamp}.png"
        download_file(video_result.cover_image_url, cover_path)
        print(f"      封面图已保存：{cover_path}")

    print("\n完成！")
    print(f"  首帧图片: {image_path}")
    print(f"  生成视频: {video_path}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用 GLM-Image 生成首帧图片，再用 CogVideoX-3 生成视频（图生视频，异步轮询）。"
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="用于生成首帧图片的文字描述（也会作为视频描述，除非另外指定 --video-prompt）。",
    )
    parser.add_argument(
        "--video-prompt",
        default=None,
        help="可选。若视频的运镜/动作描述与图片描述不同，可单独指定。",
    )
    parser.add_argument(
        "--out-dir",
        default="./outputs",
        help="输出目录，用于保存生成的图片和视频（默认：./outputs）。",
    )
    parser.add_argument(
        "--image-size",
        default="1024x1024",
        help="生成图片的分辨率（默认：1024x1024）。",
    )
    parser.add_argument(
        "--video-size",
        default="1920x1080",
        help="生成视频的分辨率（默认：1920x1080）。",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    try:
        run(
            prompt=args.prompt,
            video_prompt=args.video_prompt,
            out_dir=Path(args.out_dir),
            image_size=args.image_size,
            video_size=args.video_size,
        )
    except (BigModelAPIError, TimeoutError, requests.RequestException) as exc:
        print(f"\n[错误] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
