#!/usr/bin/env python3
"""
create_deployment.py

用途：
    通过 AutoDL 的“弹性部署”开放 API，创建一个常驻推理服务部署：
      - 固定维持 3 个副本（replica）
      - 某个副本异常退出 / 被回收后，由 AutoDL 自动重新拉起补齐（自愈）
      - 每个副本使用 GPU：RTX 4090 x 1 张卡

依赖：
    仅使用第三方库 `requests` 直接发起 HTTP 请求（不使用官方 SDK）。
    运行前请先安装：pip install requests

鉴权：
    AutoDL API Token 通过环境变量 AUTODL_TOKEN 传入，不在代码中硬编码。
    Token 获取方式：AutoDL 控制台 -> 账号设置 / 开发者选项 -> API Token。
    使用前执行：
        export AUTODL_TOKEN="你的真实 Token"

!!! 重要声明 !!!
    编写本脚本时未联网核对 AutoDL 最新版官方 API 文档，下面的：
      - API_BASE_URL / CREATE_DEPLOYMENT_PATH（接口域名与路径）
      - 请求体各字段名称、层级结构、取值（尤其是 deployment_type 的
        具体枚举字符串、GPU 型号的合法写法、镜像/启动命令相关字段）
    均是基于对 AutoDL“弹性部署”产品功能的理解构造的“最佳猜测”版本。
    在正式使用前，请务必对照 AutoDL 官方最新开放 API 文档
    （AutoDL 控制台 -> 文档中心 -> 开放 API）逐项核实并按需调整，
    否则直接调用很可能会因字段不匹配而报错或行为不符合预期。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

import requests

# --------------------------------------------------------------------------
# 基础配置
# --------------------------------------------------------------------------

# AutoDL 开放 API 域名。如与官方文档不符，可通过环境变量覆盖，或直接修改此处。
API_BASE_URL = os.environ.get("AUTODL_API_BASE", "https://api.autodl.com")

# 创建弹性部署的接口路径（占位值，请对照官方文档核实后按需调整）。
CREATE_DEPLOYMENT_PATH = "/api/v1/dev/deployment"

# API Token：出于安全考虑不写死在代码里，从环境变量读取。
AUTODL_TOKEN_ENV_VAR = "AUTODL_TOKEN"

REQUEST_TIMEOUT_SECONDS = 30


def get_api_token() -> str:
    """从环境变量读取 API Token，缺失时给出明确报错而不是发起无效请求。"""
    token = os.environ.get(AUTODL_TOKEN_ENV_VAR, "").strip()
    if not token:
        raise RuntimeError(
            f"未检测到环境变量 {AUTODL_TOKEN_ENV_VAR}。\n"
            f"请先执行：export {AUTODL_TOKEN_ENV_VAR}='你的 AutoDL API Token' 后再运行本脚本。"
        )
    return token


def build_headers(token: str) -> Dict[str, str]:
    """构造请求头。AutoDL 开放 API 通常通过 Authorization 头传递 Token。"""
    return {
        "Authorization": token,
        "Content-Type": "application/json",
    }


def build_payload() -> Dict[str, Any]:
    """
    构造创建弹性部署所需的请求体。

    关于 deployment_type 的选型说明：
        AutoDL 弹性部署支持两类副本调控策略（概念上）：
          * "fixed"   固定副本数模式：始终维持指定数量的副本运行，
                      某个副本异常退出 / 被系统回收后，AutoDL 会自动
                      重新调度、补拉起新副本，副本数量本身不随负载波动。
          * "scaling" 区间自动伸缩模式：在 [min_replica_num, max_replica_num]
                      区间内，根据负载指标（如 GPU 利用率 / 请求量）自动
                      增减副本数量。

        本任务的需求是“常驻服务、固定维持 3 个副本、副本挂了自动补上”，
        核心诉求是“恒定副本数 + 故障自愈”，而不是“根据流量自动扩缩容”，
        因此选择 deployment_type = "fixed"，并将副本数固定为 3
        （min_replica_num = max_replica_num = replica_num = 3）。
        故障自愈（挂了自动补上）是弹性部署的内置能力，通过健康检查 /
        auto_restart 配置体现，不需要额外的扩缩容逻辑。
    """
    payload: Dict[str, Any] = {
        # 部署名称，需在账号内唯一，可自行修改
        "name": "inference-service-standing",

        # 部署类型：固定副本数模式（区别于按负载自动伸缩的 "scaling" 模式）
        "deployment_type": "fixed",

        # 固定副本数：始终维持 3 个副本；副本挂掉后自动重新调度补齐
        "replica_num": 3,
        # 部分接口版本使用 min/max 表达“固定副本数”语义，这里一并给出以兼容：
        # min == max == replica_num 即表示不做自动伸缩，只维持固定数量。
        "min_replica_num": 3,
        "max_replica_num": 3,

        # 健康检查与自愈：副本异常退出 / 健康检查失败时自动重启或重新调度新副本
        "auto_restart": True,
        "health_check": {
            "enabled": True,
            # 健康检查探测路径，请替换为你的推理服务实际提供的健康检查接口
            "path": "/health",
            "port": 6006,
            "interval_seconds": 30,
            "timeout_seconds": 5,
            "failure_threshold": 3,
        },

        # 容器 / 运行环境模板
        "container_template": {
            # 镜像：请替换为你自己的推理服务镜像（可基于 AutoDL 官方基础镜像构建）
            "image": "your-registry/your-inference-image:latest",

            # 容器启动命令，请替换为实际启动推理服务的命令
            "cmd": "python3 -u server.py --port 6006",

            # 服务监听端口，请按实际推理服务端口调整
            "port": 6006,

            # 可选：环境变量，按需增删
            "env_vars": {
                # "MODEL_NAME": "your-model-name",
            },

            # 可选：数据盘挂载等，按需增删
            # "data_volumes": [],
        },

        # GPU 资源需求：RTX 4090，每个副本 1 张卡
        "gpu_resource": {
            "gpu_name_set": ["RTX 4090"],
            "gpu_num": 1,
        },
    }
    return payload


def create_deployment(payload: Dict[str, Any], token: str) -> Dict[str, Any]:
    """调用 AutoDL 弹性部署创建接口，返回解析后的 JSON 响应。"""
    url = f"{API_BASE_URL}{CREATE_DEPLOYMENT_PATH}"
    headers = build_headers(token)

    response = requests.post(
        url,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"创建弹性部署失败：HTTP {response.status_code}\n响应内容：{response.text}"
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(f"响应不是合法 JSON：{response.text}") from exc

    return result


def main() -> int:
    try:
        token = get_api_token()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    payload = build_payload()
    print("即将创建弹性部署，请求体如下：")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n请求地址：POST {API_BASE_URL}{CREATE_DEPLOYMENT_PATH}\n")

    try:
        result = create_deployment(payload, token)
    except Exception as exc:  # noqa: BLE001 - 顶层捕获后统一打印退出
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("创建成功，返回结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
