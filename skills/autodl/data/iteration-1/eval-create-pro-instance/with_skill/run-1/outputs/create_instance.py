#!/usr/bin/env python3
"""
调用 AutoDL 容器实例 Pro API，创建一台 RTX 4090 GPU 实例（使用私有镜像启动），
并轮询实例状态直到变为 running。

前置条件（详见 AutoDL 技能包 autodl/references/instances.md）：
  1. 账号已完成个人实名认证或企业认证（容器实例 Pro API 的门槛）。
  2. 已在控制台 -> 账号 -> 设置 -> 开发者Token 里生成 Token，
     通过环境变量 AUTODL_TOKEN 传入（注意：请求头是 "Authorization: <token>"，
     不带 "Bearer " 前缀，这是 AutoDL 和大多数平台不一样的地方）。
  3. 已知要启动的私有镜像的 image_uuid（可通过 image/private/list 接口查到），
     通过环境变量 AUTODL_IMAGE_UUID 传入。

本脚本只使用标准库 requests 直接调用 HTTP 接口，不使用任何 AutoDL SDK。
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

import requests

BASE_URL = "https://api.autodl.com"

# 容器实例 Pro API 专用的 GPU 型号标识（gpu_spec_uuid），不是型号名称字符串。
# 对照 autodl/references/instances.md 里的"GPU 规格 ID 对照表"：
#   网页显示 "4090-48G"（通用型） -> gpu_spec_uuid = "v-48g"
# 这是该对照表里与 "RTX 4090" 对应的条目（AutoDL 上常规 RTX 4090 实例即以此规格出售，
# 48G 指的是该型号显存扩容版本，芯片仍是 RTX 4090）。
# 注意：这张表官方本身也在持续增补新规格，如果调用报"规格不存在"，
# 请去控制台创建实例页面核对最新的 gpu_spec_uuid，不要死记这里的值。
GPU_SPEC_UUID_RTX_4090 = "v-48g"


class AutoDLAPIError(RuntimeError):
    """AutoDL 接口返回 code != "Success" 时抛出。"""


def _request(method: str, path: str, token: str, **kwargs: Any) -> Any:
    """统一发起请求并解析 AutoDL 的通用响应结构 {code, msg, data}。"""
    url = f"{BASE_URL}{path}"
    headers = kwargs.pop("headers", {})
    # AutoDL 鉴权没有 Bearer 前缀，直接是 token 本身。
    headers["Authorization"] = token

    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()
    body = resp.json()

    # 响应体统一结构：{"code": "Success"/其他, "msg": "", "data": ...}
    # code 不等于 "Success" 即视为出错；文档没有提供稳定的错误码枚举，
    # 只能靠 msg 文本判断原因，这里统一包装成异常抛出。
    if body.get("code") != "Success":
        raise AutoDLAPIError(
            f"AutoDL API 调用失败: path={path}, code={body.get('code')}, "
            f"msg={body.get('msg')}, request_id={body.get('request_id')}"
        )
    return body.get("data")


def create_pro_instance(
    token: str,
    image_uuid: str,
    gpu_spec_uuid: str = GPU_SPEC_UUID_RTX_4090,
    req_gpu_amount: int = 1,
    expand_system_disk_by_gb: int = 0,
    cuda_v_from: int = 118,
    data_center_list: Optional[list[str]] = None,
    instance_name: Optional[str] = None,
    start_command: Optional[str] = None,
) -> str:
    """创建一台按量计费的容器实例（Pro API 目前只支持按量计费）。

    返回新建实例的 instance_uuid。
    """
    payload: dict[str, Any] = {
        "gpu_spec_uuid": gpu_spec_uuid,
        "req_gpu_amount": req_gpu_amount,
        "image_uuid": image_uuid,
        "expand_system_disk_by_gb": expand_system_disk_by_gb,
        # cuda_v_from: 调度机器最低需支持的 CUDA 版本，整数编码（去掉版本号里的点，
        # 例如 11.8 -> 118）。
        "cuda_v_from": cuda_v_from,
    }
    if data_center_list:
        payload["data_center_list"] = data_center_list
    if instance_name:
        payload["instance_name"] = instance_name
    if start_command:
        payload["start_command"] = start_command

    # 创建成功时 data 直接是 instance_uuid 字符串（不是对象），例如 "pro-76419909953e"。
    instance_uuid = _request(
        "POST", "/api/v1/dev/instance/pro/create", token, json=payload
    )
    if not isinstance(instance_uuid, str) or not instance_uuid:
        raise AutoDLAPIError(f"创建实例接口返回了意料之外的 data: {instance_uuid!r}")
    return instance_uuid


def get_instance_status(token: str, instance_uuid: str) -> str:
    """查询实例状态（比 snapshot 接口更轻量，适合轮询）。"""
    status = _request(
        "GET",
        "/api/v1/dev/instance/pro/status",
        token,
        params={"instance_uuid": instance_uuid},
    )
    if not isinstance(status, str):
        raise AutoDLAPIError(f"状态查询接口返回了意料之外的 data: {status!r}")
    return status


def wait_until_running(
    token: str,
    instance_uuid: str,
    poll_interval_seconds: float = 10.0,
    timeout_seconds: float = 20 * 60.0,
) -> str:
    """轮询实例状态直到变为 running，超时或进入失败态则抛异常。"""
    # 已知会出现的非终态/终态大致有 creating / starting / running / stopped /
    # deploying_image / error 等，文档没有给出完整状态枚举，这里只对
    # "running"（成功）做正向判断，其余一律继续轮询直到超时。
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        status = get_instance_status(token, instance_uuid)
        if status != last_status:
            print(f"[{instance_uuid}] 当前状态: {status}", file=sys.stderr)
            last_status = status
        if status == "running":
            return status
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"等待实例 {instance_uuid} 变为 running 超时"
        f"（{timeout_seconds:.0f} 秒），最后一次状态为 {last_status!r}"
    )


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN")
    if not token:
        print(
            "错误: 请通过环境变量 AUTODL_TOKEN 提供你的 AutoDL 开发者 Token"
            "（控制台 -> 账号 -> 设置 -> 开发者Token）。",
            file=sys.stderr,
        )
        return 1

    image_uuid = os.environ.get("AUTODL_IMAGE_UUID")
    if not image_uuid:
        print(
            "错误: 请通过环境变量 AUTODL_IMAGE_UUID 提供要启动的私有镜像 UUID"
            "（可用 POST /api/v1/dev/instance/pro/image/private/list 接口查询）。",
            file=sys.stderr,
        )
        return 1

    instance_name = os.environ.get("AUTODL_INSTANCE_NAME", "脚本创建的RTX4090实例")

    try:
        instance_uuid = create_pro_instance(
            token=token,
            image_uuid=image_uuid,
            gpu_spec_uuid=GPU_SPEC_UUID_RTX_4090,
            req_gpu_amount=1,
            expand_system_disk_by_gb=0,
            cuda_v_from=118,
            instance_name=instance_name,
        )
        print(f"实例创建成功: instance_uuid={instance_uuid}")

        final_status = wait_until_running(token, instance_uuid)
        print(f"实例 {instance_uuid} 已进入 {final_status} 状态。")
    except AutoDLAPIError as exc:
        print(f"AutoDL API 错误: {exc}", file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(f"超时: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"网络请求异常: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
