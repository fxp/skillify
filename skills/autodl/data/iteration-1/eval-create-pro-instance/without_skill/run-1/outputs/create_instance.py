#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 AutoDL 容器实例 Pro API 创建一台 RTX 4090 GPU 实例（基于某个私有镜像启动），
然后轮询实例状态直到变为 running。

仅使用标准库 requests 直接调用 HTTP 接口（不依赖 AutoDL 官方 SDK）。

重要说明（务必在正式使用前核对）：
    本脚本没有调用真实的 AutoDL API（没有有效 token），接口路径 / 请求体字段名 /
    响应结构是根据 AutoDL 开放平台（容器实例 Pro API，https://www.autodl.com/docs/）
    的通用风格整理的“最佳猜测”版本。实际使用前请对照你账号可见的官方文档，核对：
        1. 各接口的路径与 HTTP method
        2. 创建实例请求体的字段名（本脚本假设为 region_sign / gpu_spec_uuid /
           gpu_num / image.private_image_uuid / cmd 等）
        3. 实例状态查询接口路径，以及状态取值（本脚本假设为
           created / waiting / starting / running / stopping / shutdown /
           restarting / error 等，目标状态为 "running"）
    如字段名与真实接口不符，请按报错信息或官方文档调整。

环境变量：
    AUTODL_TOKEN            必填。AutoDL 开放平台接口 token（控制台 -> 账户 -> 开放平台）。
    AUTODL_IMAGE_UUID       必填。用于启动实例的私有镜像 uuid。
    AUTODL_REGION_SIGN      选填。部署地区代码，默认 "westDC2"。
    AUTODL_GPU_SPEC_UUID    选填。RTX 4090 对应的 GPU 规格 uuid，
                             如果不设置，会尝试调用库存接口按名称自动查找。

用法：
    export AUTODL_TOKEN="xxxxx"
    export AUTODL_IMAGE_UUID="your-private-image-uuid"
    python3 create_instance.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

API_BASE_URL = "https://api.autodl.com"

# 接口 token：出于安全考虑不要硬编码，统一从环境变量读取。
API_TOKEN = os.environ.get("AUTODL_TOKEN", "")

# 用来启动实例的私有镜像 uuid（在控制台“镜像 -> 我的镜像”里可以查到）。
PRIVATE_IMAGE_UUID = os.environ.get("AUTODL_IMAGE_UUID", "")

# 部署地区代码，不同地区的 GPU 库存不同。
REGION_SIGN = os.environ.get("AUTODL_REGION_SIGN", "westDC2")

# RTX 4090 对应的 GPU 规格 uuid。
# AutoDL 内部按“规格 uuid”而不是简单的型号字符串标识 GPU 型号，严谨做法是先调用
# GPU 库存/规格查询接口，用型号名称（如 "RTX 4090"）过滤后取得该字段。
# 如果你已经知道具体 uuid，可以直接通过 AUTODL_GPU_SPEC_UUID 环境变量传入，跳过查询步骤。
GPU_SPEC_UUID_ENV = os.environ.get("AUTODL_GPU_SPEC_UUID", "")
GPU_NAME_KEYWORD = "RTX 4090"

REQUEST_TIMEOUT = 15              # 单次 HTTP 请求超时时间（秒）
POLL_INTERVAL_SECONDS = 10        # 轮询实例状态的间隔（秒）
POLL_TIMEOUT_SECONDS = 20 * 60    # 最长轮询等待时间（秒），超时则放弃

RUNNING_STATUS = "running"
# 视为创建/启动失败、不必再继续轮询的终态
FAILED_STATUSES = {"error", "expired", "released", "shutdown"}


class AutoDLAPIError(RuntimeError):
    """AutoDL 接口返回非成功状态时抛出。"""


def _headers() -> Dict[str, str]:
    if not API_TOKEN:
        raise RuntimeError(
            "未检测到 AUTODL_TOKEN 环境变量，请先执行："
            "export AUTODL_TOKEN='你的 AutoDL 开放平台 token'"
        )
    return {
        "Authorization": API_TOKEN,
        "Content-Type": "application/json",
    }


def _request(method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    统一封装 HTTP 请求。

    假设 AutoDL 接口返回统一的信封格式：
        {"code": "Success", "msg": "...", "data": {...}}
    如果实际返回结构不同，请按需调整此处的解析逻辑。
    """
    url = f"{API_BASE_URL}{path}"
    resp = requests.request(
        method,
        url,
        headers=_headers(),
        json=json_body,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    try:
        payload = resp.json()
    except ValueError as exc:
        raise AutoDLAPIError(f"接口 {path} 返回内容不是合法 JSON: {resp.text[:500]}") from exc

    code = payload.get("code")
    if code not in ("Success", "success", 0, "0"):
        raise AutoDLAPIError(f"调用 {path} 失败，返回: {payload}")

    return payload.get("data") or {}


def find_gpu_spec_uuid(region_sign: str, gpu_name_keyword: str = GPU_NAME_KEYWORD) -> str:
    """
    通过 GPU 库存/规格查询接口，按名称关键字（如 "RTX 4090"）找到对应的 gpu_spec_uuid。

    假设接口为 POST /api/v1/gpu/stock，返回 data.list 中每项包含 gpu_name 与
    gpu_spec_uuid 字段。如与实际接口不符，请按官方文档调整。
    """
    data = _request("POST", "/api/v1/gpu/stock", json_body={"region_sign": region_sign})
    items: List[Dict[str, Any]] = data.get("list", [])
    for item in items:
        if gpu_name_keyword in item.get("gpu_name", ""):
            spec_uuid = item.get("gpu_spec_uuid")
            if spec_uuid:
                print(f"[GPU 规格] 找到 {item.get('gpu_name')} -> gpu_spec_uuid = {spec_uuid}")
                return spec_uuid
    raise RuntimeError(
        f"在地区 '{region_sign}' 未找到名称包含 '{gpu_name_keyword}' 的 GPU 规格，"
        "请确认该地区是否有货，或直接通过 AUTODL_GPU_SPEC_UUID 手动指定。"
    )


def create_instance(
    gpu_spec_uuid: str,
    private_image_uuid: str,
    region_sign: str = REGION_SIGN,
    gpu_num: int = 1,
) -> str:
    """
    创建一台容器实例，返回 instance_uuid。

    假设接口为 POST /api/v1/instance，请求体字段：
        region_sign          部署地区
        gpu_spec_uuid         GPU 规格（这里对应 RTX 4090）
        gpu_num               GPU 数量
        image.type            "private" 表示使用私有镜像
        image.private_image_uuid  私有镜像 uuid
        cmd                    容器启动后执行的保活命令；如果私有镜像自身已有
                                常驻前台进程（如启动了 SSH/Jupyter 服务），可以去掉这一项
    """
    if not private_image_uuid:
        raise RuntimeError(
            "缺少私有镜像 uuid，请通过 AUTODL_IMAGE_UUID 环境变量指定。"
        )

    body: Dict[str, Any] = {
        "region_sign": region_sign,
        "gpu_spec_uuid": gpu_spec_uuid,
        "gpu_num": gpu_num,
        "image": {
            "type": "private",
            "private_image_uuid": private_image_uuid,
        },
        "cmd": "sleep infinity",
    }

    data = _request("POST", "/api/v1/instance", json_body=body)
    instance_uuid = data.get("instance_uuid") or data.get("uuid")
    if not instance_uuid:
        raise AutoDLAPIError(f"创建实例接口未返回 instance_uuid，原始返回: {data}")

    print(f"[创建成功] instance_uuid = {instance_uuid}")
    return instance_uuid


def get_instance_status(instance_uuid: str) -> str:
    """
    查询实例当前状态。

    假设接口为 POST /api/v1/instance/list，请求体传入 instance_uuid_list 做过滤，
    返回 data.list 中每项包含 status 字段。

    AutoDL 实例状态常见取值（供参考，具体以官方文档为准）：
        created     创建中
        waiting     等待开机
        starting    开机中
        running     运行中（目标状态）
        stopping    关机中
        shutdown    已关机
        restarting  重启中
        error       异常
    """
    data = _request(
        "POST",
        "/api/v1/instance/list",
        json_body={"instance_uuid_list": [instance_uuid]},
    )
    instances: List[Dict[str, Any]] = data.get("list", [])
    if not instances:
        raise AutoDLAPIError(f"未查询到实例 {instance_uuid} 的信息")
    return instances[0].get("status", "")


def wait_until_running(
    instance_uuid: str,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    timeout: int = POLL_TIMEOUT_SECONDS,
) -> None:
    """轮询实例状态，直到变为 running，或者进入失败终态 / 超时后抛出异常。"""
    start = time.monotonic()
    last_status: Optional[str] = None

    while True:
        status = get_instance_status(instance_uuid)

        if status != last_status:
            elapsed = int(time.monotonic() - start)
            print(f"[{elapsed:>4}s] 实例状态: {status}")
            last_status = status

        if status == RUNNING_STATUS:
            print("实例已进入 running 状态。")
            return

        if status in FAILED_STATUSES:
            raise RuntimeError(f"实例进入异常终止状态: {status}，停止轮询。")

        if time.monotonic() - start > timeout:
            raise TimeoutError(
                f"等待实例进入 running 状态超时（{timeout} 秒），当前状态: {status}"
            )

        time.sleep(poll_interval)


def main() -> int:
    try:
        gpu_spec_uuid = GPU_SPEC_UUID_ENV or find_gpu_spec_uuid(REGION_SIGN, GPU_NAME_KEYWORD)

        instance_uuid = create_instance(
            gpu_spec_uuid=gpu_spec_uuid,
            private_image_uuid=PRIVATE_IMAGE_UUID,
            region_sign=REGION_SIGN,
            gpu_num=1,
        )

        wait_until_running(instance_uuid)

    except Exception as exc:  # noqa: BLE001 - 顶层统一捕获，打印后以非零状态退出
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
