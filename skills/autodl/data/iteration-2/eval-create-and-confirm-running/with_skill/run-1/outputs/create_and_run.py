#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 AutoDL 容器实例 Pro API 创建一台按量计费的 GPU 实例，并确保它创建完成后
处于 "running" 状态，可以马上开始使用。

只用标准库 requests 直接调用 HTTP 接口，不依赖任何 AutoDL 官方 SDK。

前提条件（写在这里而不是等报错才知道）：
    - AutoDL 账号必须已完成"个人实名认证"或"企业认证"。
      未认证账号调用创建接口会被直接拒绝，返回：
          {"code": "TORealName", "msg": "未完成实名认证,认证后才可使用"}
      这是账号资质问题，不是参数错误，重试没有意义，需要去控制台完成认证。
    - Token 从控制台 -> 账号 -> 设置 -> 开发者Token 获取，通过环境变量
      AUTODL_TOKEN 传入（脚本里只放占位符，不硬编码真实 token）。

关键接口行为（均来自 AutoDL 容器实例 Pro API 文档 + 实测记录）：
    - Base URL: https://api.autodl.com
    - 鉴权：请求头 Authorization: <token>，注意没有 "Bearer " 前缀。
    - POST /api/v1/dev/instance/pro/create 创建实例成功后，实例会自动开机，
      不需要、也不应该在创建成功后额外调用一次 power_on（power_on 只用于
      重启一台"之前被关过机"的实例）。
    - 创建后状态会先短暂处于 "starting"，随后变为 "running"；脚本通过轮询
      GET /api/v1/dev/instance/pro/status 等待状态变为 "running"，
      并把 "starting" 当作"还没就绪"而不是异常来处理。
    - 两个 GET 接口（snapshot、status）的参数必须放进 URL 查询字符串
      （requests 的 params=），而不是 JSON body —— 官方文档示例本身把这一点
      写错了，实测放进 json= 会返回 RequestParameterIsWrong。
    - 所有响应体统一是 {"code": ..., "msg": ..., "data": ...} 结构，
      code != "Success" 就是出错，没有稳定的数字错误码可用，只能按 code
      字符串 + msg 文本做判断。

用法：
    export AUTODL_TOKEN="你的开发者token"
    python create_and_run.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://api.autodl.com"

# ---------------------------------------------------------------------------
# 实例创建参数 —— 按需通过环境变量覆盖，未设置时使用下面的默认值。
# gpu_spec_uuid 对照表见 autodl 技能包 references/instances.md，
# 这里默认用 4090-48G（通用型）对应的 "v-48g"。
# ---------------------------------------------------------------------------
GPU_SPEC_UUID = os.environ.get("AUTODL_GPU_SPEC_UUID", "v-48g")
REQ_GPU_AMOUNT = int(os.environ.get("AUTODL_REQ_GPU_AMOUNT", "1"))
# 默认用一个公共 PyTorch 基础镜像，可通过环境变量替换成自己的私有镜像 UUID。
IMAGE_UUID = os.environ.get("AUTODL_IMAGE_UUID", "base-image-l2t43iu6uk")
EXPAND_SYSTEM_DISK_BY_GB = int(os.environ.get("AUTODL_EXPAND_SYSTEM_DISK_BY_GB", "0"))
# CUDA 版本用整数编码，去掉版本号里的点：11.8 -> 118
CUDA_V_FROM = int(os.environ.get("AUTODL_CUDA_V_FROM", "118"))
INSTANCE_NAME = os.environ.get("AUTODL_INSTANCE_NAME", "API创建的实例")
# 候选地区列表，留空则由系统自动选择
DATA_CENTER_LIST = [
    dc.strip()
    for dc in os.environ.get("AUTODL_DATA_CENTER_LIST", "").split(",")
    if dc.strip()
]

# 轮询等待 running 的超时与间隔（秒）
POLL_INTERVAL_SECONDS = float(os.environ.get("AUTODL_POLL_INTERVAL_SECONDS", "5"))
POLL_TIMEOUT_SECONDS = float(os.environ.get("AUTODL_POLL_TIMEOUT_SECONDS", "300"))

# 创建实例后、实例还没变成 running 之前，可能出现的“正在启动中”的中间态。
# 这些状态不是错误，只是还没到 running，轮询要继续等待。
TRANSIENT_STATES = {"starting"}
TARGET_STATE = "running"


class AutoDLAPIError(RuntimeError):
    """AutoDL 接口返回 code != "Success" 时抛出的通用错误。"""

    def __init__(self, code: str, msg: str, request_id: Optional[str] = None):
        self.code = code
        self.msg = msg
        self.request_id = request_id
        super().__init__(f"AutoDL API error: code={code!r} msg={msg!r} request_id={request_id!r}")


class NotRealNameVerifiedError(AutoDLAPIError):
    """账号未完成实名认证/企业认证，无法创建实例。这是账号资质问题，不是参数错误，重试没有意义。"""


def _headers(token: str) -> Dict[str, str]:
    # 注意：AutoDL 的鉴权没有 "Bearer " 前缀，直接就是 token 本身。
    return {"Authorization": token}


def _unwrap(resp: requests.Response) -> Any:
    """统一解析 AutoDL 的响应体 {"code", "msg", "data", "request_id"}。

    code == "Success" 时返回 data 字段；否则按 code 抛出对应异常。
    """
    resp.raise_for_status()
    payload = resp.json()
    code = payload.get("code")
    msg = payload.get("msg", "")
    request_id = payload.get("request_id")

    if code == "Success":
        return payload.get("data")

    if code == "TORealName":
        raise NotRealNameVerifiedError(code, msg, request_id)

    raise AutoDLAPIError(code, msg, request_id)


def create_instance(token: str) -> str:
    """创建一台按量计费的容器实例 Pro，返回新实例的 instance_uuid。

    创建成功后实例会自动开机启动，这里不会、也不需要额外调用 power_on。
    """
    body: Dict[str, Any] = {
        "req_gpu_amount": REQ_GPU_AMOUNT,
        "expand_system_disk_by_gb": EXPAND_SYSTEM_DISK_BY_GB,
        "gpu_spec_uuid": GPU_SPEC_UUID,
        "image_uuid": IMAGE_UUID,
        "cuda_v_from": CUDA_V_FROM,
        "instance_name": INSTANCE_NAME,
    }
    if DATA_CENTER_LIST:
        body["data_center_list"] = DATA_CENTER_LIST

    resp = requests.post(
        f"{BASE_URL}/api/v1/dev/instance/pro/create",
        headers=_headers(token),
        json=body,
        timeout=30,
    )
    instance_uuid = _unwrap(resp)
    if not isinstance(instance_uuid, str):
        raise RuntimeError(f"意料之外的响应格式，data 应为 instance_uuid 字符串，实际为: {instance_uuid!r}")
    return instance_uuid


def get_instance_status(token: str, instance_uuid: str) -> str:
    """查询实例状态。GET 接口必须用 URL 查询字符串（params=），不能用 json body。"""
    resp = requests.get(
        f"{BASE_URL}/api/v1/dev/instance/pro/status",
        headers=_headers(token),
        params={"instance_uuid": instance_uuid},
        timeout=30,
    )
    status = _unwrap(resp)
    if not isinstance(status, str):
        raise RuntimeError(f"意料之外的响应格式，data 应为状态字符串，实际为: {status!r}")
    return status


def wait_until_running(
    token: str,
    instance_uuid: str,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    timeout_seconds: float = POLL_TIMEOUT_SECONDS,
) -> str:
    """轮询实例状态，直到变为 running 或超时。

    - "starting" 视为正常的中间态（还在启动中），继续等待，不当异常处理。
    - 其他任何状态（包括 shutdown/shutting_down 等）都不是本流程期望出现的，
      直接抛错，避免脚本假装“成功”却其实实例没在跑。
    """
    deadline = time.monotonic() + timeout_seconds
    last_status = None

    while time.monotonic() < deadline:
        status = get_instance_status(token, instance_uuid)
        last_status = status

        if status == TARGET_STATE:
            return status

        if status in TRANSIENT_STATES:
            time.sleep(poll_interval_seconds)
            continue

        # 出现了既不是目标状态、也不是已知的启动中间态的状态，
        # 说明流程走偏了（比如实例莫名其妙关机了），不要继续傻等。
        raise RuntimeError(
            f"实例 {instance_uuid} 处于非预期状态 {status!r}（既不是 {TARGET_STATE!r} 也不是启动中间态 {TRANSIENT_STATES!r}），"
            "停止轮询，请去控制台确认实例情况。"
        )

    raise TimeoutError(
        f"等待实例 {instance_uuid} 变为 {TARGET_STATE!r} 超时（{timeout_seconds} 秒），最后一次观测到的状态为 {last_status!r}。"
    )


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN")
    if not token:
        print(
            "错误：未设置环境变量 AUTODL_TOKEN。\n"
            "请先执行：export AUTODL_TOKEN=\"你的开发者token\"（控制台 -> 账号 -> 设置 -> 开发者Token 获取）",
            file=sys.stderr,
        )
        return 1

    print(f"[1/3] 正在创建实例（gpu_spec_uuid={GPU_SPEC_UUID}, req_gpu_amount={REQ_GPU_AMOUNT}）...")
    try:
        instance_uuid = create_instance(token)
    except NotRealNameVerifiedError as e:
        print(
            "错误：账号未完成实名认证/企业认证，无法创建实例。\n"
            "这不是参数问题、也不是重试能解决的问题，请先去 AutoDL 控制台完成实名认证再运行本脚本。\n"
            f"原始错误：{e}",
            file=sys.stderr,
        )
        return 1
    except AutoDLAPIError as e:
        if e.code == "InternalError" and "库存" in e.msg:
            print(
                f"错误：当前算力规格 {GPU_SPEC_UUID!r} 暂无库存。\n"
                "这只是临时缺货，不是账号权限问题也不是代码写错了，"
                "换一个 gpu_spec_uuid（AUTODL_GPU_SPEC_UUID 环境变量）或稍后重试即可。\n"
                f"原始错误：{e}",
                file=sys.stderr,
            )
        else:
            print(f"创建实例失败：{e}", file=sys.stderr)
        return 1

    print(f"      实例已创建：instance_uuid={instance_uuid}")

    print(f"[2/3] 正在等待实例进入 {TARGET_STATE!r} 状态（不会重复调用开机接口——创建后已自动开机）...")
    try:
        final_status = wait_until_running(token, instance_uuid)
    except (TimeoutError, RuntimeError) as e:
        print(
            f"等待实例就绪失败：{e}\n"
            f"实例 instance_uuid={instance_uuid} 已创建，请手动去控制台或用 status 接口确认状态，避免产生不必要的计费。",
            file=sys.stderr,
        )
        return 1

    print(f"[3/3] 实例已就绪：instance_uuid={instance_uuid} status={final_status!r}，可以立即开始使用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
