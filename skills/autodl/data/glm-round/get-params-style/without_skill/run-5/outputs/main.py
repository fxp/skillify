#!/usr/bin/env python3
"""查询一台 AutoDL 容器实例的当前状态。

用法：
    export AUTODL_TOKEN=<控制台-设置-开发者Token>
    export AUTODL_INSTANCE_UUID=<实例UUID，例如 pro-76576c61fdf1>
    python3 main.py

排查时最需要区分两种失败，本脚本用不同的提示与退出码分开它们：
    退出码 0  —— 查询成功，打印实例状态
    退出码 2  —— 实例不存在（UUID 对应的实例查不到：已释放/抄错/属于别的账号）
    退出码 3  —— 请求本身有误（Token 无效、参数缺失、接口地址变更、权限/认证不满足等）
    退出码 4  —— 服务端/网络异常（既非实例问题也非请求写错，稍后重试或找官方）

接口依据官方文档（容器实例Pro API）：
    GET https://api.autodl.com/api/v1/dev/instance/pro/status
    鉴权头 Authorization 直接放裸 token（不带 Bearer），参数 instance_uuid 放 JSON body。
    官方未公开错误码表，因此「实例不存在」按 code/msg 的文本特征识别。
"""

import json
import os
import sys

import requests

API_URL = "https://api.autodl.com/api/v1/dev/instance/pro/status"
TIMEOUT_SECONDS = 15

EXIT_OK = 0
EXIT_INSTANCE_NOT_FOUND = 2
EXIT_REQUEST_ERROR = 3
EXIT_SERVER_ERROR = 4

# code/msg 命中任一特征即判定为「实例不存在」（官方无错误码表，按文本特征兜底）
NOT_EXIST_MARKERS = (
    "instancenotexist",
    "instancenotfound",
    "instance not exist",
    "instance not found",
    "实例不存在",
    "实例未找到",
)


def die(category: str, message: str, exit_code: int) -> None:
    print(f"[{category}] {message}", file=sys.stderr)
    sys.exit(exit_code)


def main() -> None:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()

    # 本地配置问题也属于“请求侧”，但单独点名，避免和实例问题混淆
    if not token:
        die("请求有误", "环境变量 AUTODL_TOKEN 未设置（控制台 -> 设置 -> 开发者Token）", EXIT_REQUEST_ERROR)
    if not instance_uuid:
        die("请求有误", "环境变量 AUTODL_INSTANCE_UUID 未设置", EXIT_REQUEST_ERROR)

    try:
        resp = requests.get(
            API_URL,
            json={"instance_uuid": instance_uuid},
            headers={"Authorization": token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        die("服务端/网络异常", f"请求未能送达 {API_URL}：{exc!r}", EXIT_SERVER_ERROR)

    # HTTP 层失败：请求到达了服务器但被拒，均属“请求本身有误”，与实例是否存在无关
    if resp.status_code in (401, 403):
        die("请求有误",
            f"Token 鉴权失败（HTTP {resp.status_code}），请检查 AUTODL_TOKEN 是否正确或已过期。响应：{resp.text[:200]}",
            EXIT_REQUEST_ERROR)
    if resp.status_code == 404:
        die("请求有误",
            f"接口路径不存在（HTTP 404），API 地址可能已变更，请对照官方文档核对 {API_URL}",
            EXIT_REQUEST_ERROR)
    if 400 <= resp.status_code < 500:
        die("请求有误",
            f"客户端请求被拒绝（HTTP {resp.status_code}）：{resp.text[:200]}",
            EXIT_REQUEST_ERROR)
    if resp.status_code >= 500:
        die("服务端异常",
            f"AutoDL 服务端错误（HTTP {resp.status_code}）：{resp.text[:200]}",
            EXIT_SERVER_ERROR)

    try:
        payload = resp.json()
    except ValueError:
        die("请求有误",
            f"响应不是合法 JSON（可能被网关拦截或地址不对）：{resp.text[:200]}",
            EXIT_REQUEST_ERROR)

    code = str(payload.get("code", ""))
    msg = str(payload.get("msg", ""))
    request_id = str(payload.get("request_id", ""))
    rid = f"，request_id={request_id}" if request_id else ""

    if code == "Success":
        data = payload.get("data")
        # status 接口的 data 直接是状态字符串（如 "running"）；万一返回对象也能兜底展示
        status = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        print(f"实例 {instance_uuid} 当前状态：{status}{rid}")
        return

    combined = f"{code} {msg}".lower()
    if any(marker in combined for marker in NOT_EXIST_MARKERS):
        die("实例不存在",
            f"AutoDL 返回 code={code or '<空>'}，msg={msg or '<空>'}{rid}。"
            "这个 UUID 查不到实例：可能已被释放/删除、UUID 抄错，或实例属于其他账号——"
            "请回控制台核对实例列表里的 UUID。",
            EXIT_INSTANCE_NOT_FOUND)

    die("请求有误",
        f"AutoDL 拒绝了本次请求：code={code or '<空>'}，msg={msg or '<空>'}{rid}。"
        "问题出在请求侧而不是实例：请检查 Token 权限、UUID 参数格式，"
        "以及账号是否满足容器实例Pro API 要求的实名/企业认证。",
        EXIT_REQUEST_ERROR)


if __name__ == "__main__":
    main()
