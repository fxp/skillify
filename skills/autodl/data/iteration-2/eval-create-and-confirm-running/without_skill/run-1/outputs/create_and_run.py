#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 AutoDL 容器实例 Pro API 创建一台 GPU 实例，并轮询状态直到它变为 running
（可以立即使用）为止。

只用标准库 requests 直接发 HTTP 请求，不依赖 AutoDL 官方 SDK。

重要说明（务必先读）
--------------------
1. 本脚本是"尽力而为"版本：AutoDL Pro API 的具体字段名 / 路径请以
   官方文档（https://www.autodl.com/docs/api_new/）为准，使用前请对照
   文档核对下面标了 `# TODO/CONFIRM` 的地方（endpoint 路径、请求体字段、
   响应体里状态字段的名字和取值）。
2. AutoDL 的鉴权方式是在请求头里带上 Authorization: <token>（token 在
   AutoDL 控制台"设置 - 开发者 Token"里获取），本脚本从环境变量
   AUTODL_TOKEN 读取，不在代码里写死。
3. 关键设计点：创建实例（POST /instance）之后，实例通常处于
   "已创建但未开机"（如 created / shutdown）的状态，需要显式调用
   一次"开机 / power_on"接口才会真正启动、进入 running。因此本脚本：
      create_instance() -> 若返回状态不是 running，则调用 power_on()
                         -> 轮询 get_instance() 直到 status == running
   这样能确保脚本结束时实例确实处于可以立刻使用的运行状态，而不是
   仅仅"创建成功"就返回。
"""

from __future__ import annotations

import os
import sys
import time
import json
from typing import Any, Optional

import requests


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# AutoDL 开放 API 的 base url。# TODO/CONFIRM: 以官方文档为准，
# 常见形式类似 https://api.autodl.com。
API_BASE_URL = os.environ.get("AUTODL_API_BASE_URL", "https://api.autodl.com")

# 鉴权 token，从环境变量读取，不要把真实 token 写进代码或提交到仓库。
API_TOKEN = os.environ.get("AUTODL_TOKEN", "REPLACE_WITH_YOUR_AUTODL_TOKEN")

# 各接口路径。# TODO/CONFIRM: 请对照 AutoDL Pro API 文档核对下列路径，
# 不同版本/不同产品线（算力市场 / 容器实例）路径可能不同。
CREATE_INSTANCE_PATH = "/api/v1/instance"
GET_INSTANCE_PATH = "/api/v1/instance/{instance_uuid}"
POWER_ON_PATH = "/api/v1/instance/{instance_uuid}/power_on"

# 轮询参数
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 15 * 60  # 15 分钟超时保护

# 实例被认为"可以立刻使用"的状态值。# TODO/CONFIRM: 核对官方文档中
# 实例状态枚举的准确拼写，这里假设为 "running"。
RUNNING_STATUS = "running"

# 会导致轮询提前失败退出的终止态（避免死等一个已经失败的实例）。
# TODO/CONFIRM: 核对官方文档里失败/异常状态的准确取值。
TERMINAL_FAILURE_STATUSES = {"failed", "create_failed", "error", "shutdown_error"}


class AutoDLAPIError(RuntimeError):
    """AutoDL API 返回业务错误（HTTP 200 但 code 不是成功）或 HTTP 状态码非 2xx。"""


def _headers() -> dict:
    return {
        "Authorization": API_TOKEN,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, *, json_body: Optional[dict] = None) -> Any:
    """统一的请求封装：发请求、处理 HTTP 错误、解析 AutoDL 的通用响应结构。

    AutoDL 开放 API 的响应通常是形如：
        {"code": "Success", "msg": "...", "data": {...}}
    的包装结构。# TODO/CONFIRM: 请核对实际返回结构（成功时 code 的
    具体取值，可能是 "Success"、0、"OK" 等），并按需调整下面的判断逻辑。
    """
    url = f"{API_BASE_URL}{path}"
    resp = requests.request(method, url, headers=_headers(), json=json_body, timeout=30)

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise AutoDLAPIError(
            f"HTTP {resp.status_code} 调用 {method} {url} 失败: {resp.text}"
        ) from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        raise AutoDLAPIError(f"响应不是合法 JSON: {resp.text}") from exc

    # 常见的业务层错误判断：code 不等于成功标记时抛异常。
    code = payload.get("code")
    if code is not None and code not in ("Success", "success", 0, "0", "OK"):
        raise AutoDLAPIError(
            f"AutoDL API 业务错误: code={code}, msg={payload.get('msg')}, raw={payload}"
        )

    return payload.get("data", payload)


def create_instance() -> str:
    """创建一台 GPU 容器实例，返回实例的唯一标识（instance_uuid）。

    请求体字段仅为示例，# TODO/CONFIRM: 请按官方文档替换为真实可用的
    region_sign / gpu_name / image 等取值（可先在 AutoDL 控制台的
    "算力市场"页面手动创建一次，用浏览器开发者工具抓包确认真实字段）。
    """
    body = {
        # 地域标识，例如 "westDC2"。
        "region_sign": os.environ.get("AUTODL_REGION_SIGN", "westDC2"),
        # GPU 型号，例如 "RTX 4090"。
        "gpu_name": os.environ.get("AUTODL_GPU_NAME", "RTX 4090"),
        # 需要的 GPU 数量。
        "gpu_num": int(os.environ.get("AUTODL_GPU_NUM", "1")),
        # 镜像信息：使用官方基础镜像或自己保存的镜像，字段结构以文档为准。
        "image": {
            "base_image": os.environ.get(
                "AUTODL_BASE_IMAGE", "PyTorch/2.1.0/3.10(ubuntu22.04)/12.1"
            ),
        },
        # 实例名称，方便在控制台里辨认。
        "instance_name": os.environ.get("AUTODL_INSTANCE_NAME", "autodl-instance-via-api"),
        # 计费方式，例如按量付费 "按量付费" / "spot" 视文档定义的枚举值而定。
        "cmd_billing_type": os.environ.get("AUTODL_BILLING_TYPE", "按量付费"),
    }

    data = _request("POST", CREATE_INSTANCE_PATH, json_body=body)

    # TODO/CONFIRM: 核对创建接口返回体里实例标识字段的真实名字，
    # 这里假设叫 instance_uuid。
    instance_uuid = data.get("instance_uuid") or data.get("uuid")
    if not instance_uuid:
        raise AutoDLAPIError(f"创建实例响应中未找到 instance_uuid: {data}")

    print(f"[create_instance] 已提交创建请求，instance_uuid={instance_uuid}")
    return instance_uuid


def get_instance_status(instance_uuid: str) -> str:
    """查询实例详情，返回当前状态字符串。"""
    path = GET_INSTANCE_PATH.format(instance_uuid=instance_uuid)
    data = _request("GET", path)

    # TODO/CONFIRM: 核对状态字段名字，这里假设叫 status。
    status = data.get("status")
    if status is None:
        raise AutoDLAPIError(f"查询实例详情响应中未找到 status 字段: {data}")
    return status


def power_on(instance_uuid: str) -> None:
    """显式开机。创建接口通常只是把实例"创建"出来（处于关机/待开机状态），
    需要单独调用开机接口才会真正启动并进入 running。
    """
    path = POWER_ON_PATH.format(instance_uuid=instance_uuid)
    print(f"[power_on] 调用开机接口: instance_uuid={instance_uuid}")
    _request("POST", path)


def wait_until_running(instance_uuid: str) -> None:
    """轮询实例状态，直到变为 RUNNING_STATUS，或超时 / 进入失败终止态。"""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS

    while True:
        status = get_instance_status(instance_uuid)
        print(f"[wait_until_running] 当前状态: {status}")

        if status == RUNNING_STATUS:
            print(f"[wait_until_running] 实例 {instance_uuid} 已进入 running，可以使用。")
            return

        if status in TERMINAL_FAILURE_STATUSES:
            raise AutoDLAPIError(
                f"实例 {instance_uuid} 进入失败状态: {status}，请到 AutoDL 控制台查看详情。"
            )

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"等待实例 {instance_uuid} 进入 running 状态超时"
                f"（超过 {POLL_TIMEOUT_SECONDS} 秒），最后状态: {status}"
            )

        time.sleep(POLL_INTERVAL_SECONDS)


def main() -> int:
    if not API_TOKEN or API_TOKEN == "REPLACE_WITH_YOUR_AUTODL_TOKEN":
        print(
            "错误：未设置 AUTODL_TOKEN 环境变量。请先执行\n"
            "    export AUTODL_TOKEN=你的AutoDL开发者Token\n"
            "再运行本脚本。",
            file=sys.stderr,
        )
        return 1

    try:
        instance_uuid = create_instance()

        # 创建后先查一次状态：如果创建接口本身就已经把实例拉起来了，
        # 直接进入轮询；否则显式开机。
        status = get_instance_status(instance_uuid)
        if status != RUNNING_STATUS:
            power_on(instance_uuid)

        wait_until_running(instance_uuid)

    except (AutoDLAPIError, TimeoutError) as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {"instance_uuid": instance_uuid, "status": RUNNING_STATUS},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
