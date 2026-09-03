#!/usr/bin/env python3
"""
在 AutoDL（autodl.com）上创建一个常驻推理服务的弹性部署（Elastic Deployment）。

需求：
    - 系统自动维持 3 个副本，副本挂了自动补上
      -> 这正是弹性部署 API 里 deployment_type="ReplicaSet" 的定义
         （Job 是"批量任务跑完即止"，Container 是"单个容器无副本概念"，都不符合本需求）
    - GPU 用 RTX 4090，1 张卡
      -> 弹性部署 API 用 gpu_name_set（型号名称字符串）而不是容器实例 Pro API 里的
         gpu_spec_uuid，这里填 ["RTX 4090"]；gpu_num=1 表示单个容器占 1 张卡

前置条件（写代码前务必和用户确认，否则调用必然失败）：
    1. AutoDL 账号必须完成【企业认证】——弹性部署 API 的认证门槛比容器实例 Pro API
       （个人实名或企业认证均可）更高，个人实名认证不够用。
    2. 已经在 AutoDL 控制台（网页端）保存好一个可用的私有镜像，或使用平台提供的公共
       基础镜像 UUID——弹性部署不支持从外部导入镜像。
    3. 已经从 控制台 → 账号 → 设置 → 开发者Token 拿到 API Token，并设置到环境变量
       AUTODL_TOKEN 中（本脚本不接受在代码里硬编码 token）。

用法：
    export AUTODL_TOKEN="your_real_token_here"
    python create_deployment.py

本脚本只使用标准库 + requests，直接调用 AutoDL 的 HTTP REST 接口，不依赖任何 SDK。
"""

from __future__ import annotations

import os
import sys
from typing import Any

import requests

# AutoDL API 固定 base url
BASE_URL = "https://api.autodl.com"

# 鉴权注意：AutoDL 和大多数平台不一样，Authorization 头直接就是 token 本身，
# 没有 "Bearer " 前缀。
AUTODL_TOKEN = os.environ.get("AUTODL_TOKEN")


def _request(method: str, path: str, **kwargs: Any) -> dict:
    """统一发起请求并做 AutoDL 约定的错误处理。

    AutoDL 响应体统一结构为 {"code": "Success"/其他, "msg": "", "data": ...}。
    code 不等于 "Success" 即视为出错；官方文档没有提供稳定的错误码枚举，
    只能依赖 msg 的文本内容判断原因，因此这里不对 msg 做 switch/case，
    只是把它原样抛出给调用方查看。
    """
    url = f"{BASE_URL}{path}"
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = AUTODL_TOKEN

    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    resp.raise_for_status()  # 先处理 HTTP 层面的错误（网络/鉴权失败等）

    payload = resp.json()
    if payload.get("code") != "Success":
        raise RuntimeError(
            f"AutoDL API 调用失败: path={path}, code={payload.get('code')!r}, "
            f"msg={payload.get('msg')!r}"
        )
    return payload["data"]


def create_replica_set_deployment(
    *,
    name: str,
    image_uuid: str,
    cmd: str,
    replica_num: int = 3,
    dc_list: list[str] | None = None,
    gpu_name: str = "RTX 4090",
    gpu_num: int = 1,
) -> dict:
    """创建一个 ReplicaSet 类型的弹性部署：常驻维持固定副本数，副本挂了自动补。

    Args:
        name: 部署名称。
        image_uuid: 私有镜像 UUID 或公共基础镜像 UUID（弹性部署不支持外部导入镜像）。
        cmd: 容器启动命令，即推理服务的启动脚本/命令。
        replica_num: 期望维持的副本数量，默认 3。
        dc_list: 可调度地区列表，默认使用文档推荐的西北企业区 + 西北B区两个区，
                 扩大可调度范围、降低排队等待概率。
        gpu_name: GPU 型号名称字符串（注意不是 gpu_spec_uuid）。
        gpu_num: 单个容器所需 GPU 数量。

    Returns:
        创建成功后的 data 字段，包含 deployment_uuid。
    """
    if dc_list is None:
        dc_list = ["westDC2", "westDC3"]

    body = {
        "name": name,
        "deployment_type": "ReplicaSet",
        "replica_num": replica_num,
        # 复用已停止的容器可以显著提升后续扩容/重建副本的速度
        "reuse_container": True,
        "reuse_container_scope": "all",
        "container_template": {
            "dc_list": dc_list,
            "gpu_name_set": [gpu_name],
            "gpu_num": gpu_num,
            # CUDA 版本范围：113~128 覆盖绝大多数框架需求；
            # 选型原则见 skill 文档——找不到精确对应版本时选"兼容所需版本的最低可选值"，
            # 避免选得过高导致可调度机器范围变窄。
            "cuda_v_from": 113,
            "cuda_v_to": 128,
            "cpu_num_from": 1,
            "cpu_num_to": 100,
            "memory_size_from": 1,
            "memory_size_to": 256,
            # 价格单位是"元 x 1000"的整数：0.01 元/小时 ~ 9 元/小时
            "price_from": 10,
            "price_to": 9000,
            "image_uuid": image_uuid,
            "cmd": cmd,
        },
    }

    return _request("POST", "/api/v1/dev/deployment", json=body)


def main() -> int:
    if not AUTODL_TOKEN:
        print(
            "错误：未设置环境变量 AUTODL_TOKEN。\n"
            "请先执行: export AUTODL_TOKEN=\"your_real_token_here\"\n"
            "Token 获取位置：AutoDL 控制台 -> 账号 -> 设置 -> 开发者Token。\n"
            "另外请确认账号已完成【企业认证】——弹性部署 API 要求企业认证，"
            "个人实名认证不够用，认证不够会导致下面的调用直接失败。",
            file=sys.stderr,
        )
        return 1

    # TODO: 替换成你自己在 AutoDL 控制台保存好的私有镜像 UUID，
    # 或替换成 references/elastic-deployment.md 附录里的公共基础镜像 UUID。
    image_uuid = "image-db8346e037"

    # TODO: 替换成你的推理服务真正的启动命令，
    # 例如: "python -m vllm.entrypoints.openai.api_server --model /root/model --port 6006"
    cmd = "python -m my_inference_service --port 6006"

    try:
        data = create_replica_set_deployment(
            name="inference-service-replicaset",
            image_uuid=image_uuid,
            cmd=cmd,
            replica_num=3,
            gpu_name="RTX 4090",
            gpu_num=1,
        )
    except requests.exceptions.RequestException as exc:
        print(f"网络请求失败: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    deployment_uuid = data.get("deployment_uuid")
    print("部署创建成功！")
    print(f"deployment_uuid = {deployment_uuid}")
    print(
        "该部署为 ReplicaSet 类型，会自动维持 3 个副本，副本异常退出后系统会自动补新副本，"
        "无需额外的健康检查/自愈脚本。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
