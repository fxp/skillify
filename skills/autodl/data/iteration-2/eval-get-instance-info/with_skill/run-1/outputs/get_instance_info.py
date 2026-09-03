#!/usr/bin/env python3
"""
查询 AutoDL 容器实例（Pro）的详细信息，重点是 SSH 连接方式。

用法：
    export AUTODL_TOKEN="your_token"          # 控制台 -> 账号 -> 设置 -> 开发者Token
    export AUTODL_INSTANCE_UUID="pro-xxxxxxxx" # 目标实例的 instance_uuid
    python get_instance_info.py

依赖：只用标准库 + requests（pip install requests）。
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
SNAPSHOT_ENDPOINT = f"{BASE_URL}/api/v1/dev/instance/pro/snapshot"


def get_instance_snapshot(token: str, instance_uuid: str) -> dict:
    """
    调用"获取实例详情"接口，拿到实例的完整快照（SSH/Jupyter/端口映射/资源使用率等）。

    关键点：
    - 这是一个 GET 接口，instance_uuid 必须通过 URL 查询字符串（params）传递，
      不能放进 JSON body。AutoDL 官方文档这里的示例代码本身是错的（示例展示的是
      "请求 Body 示例"），实测把参数放进 requests.get(url, json=...) 的 body 会
      直接返回 {"code": "RequestParameterIsWrong", "msg": "请求参数错误"}；
      改用 requests.get(url, params=...) 才能被正确解析。
    - 鉴权头是 Authorization: <token>，没有 "Bearer " 前缀。
    """
    headers = {"Authorization": token}
    params = {"instance_uuid": instance_uuid}

    resp = requests.get(SNAPSHOT_ENDPOINT, headers=headers, params=params, timeout=15)
    resp.raise_for_status()  # 处理 HTTP 层面的错误（网络问题、5xx 等）

    body = resp.json()

    # AutoDL 响应体统一结构：{"code": "Success"/其他, "msg": "", "data": ...}
    # code 不等于 "Success" 即视为业务错误，错误信息在 msg 里（没有稳定的错误码枚举，
    # 只能靠 msg 文本判断原因）。
    if body.get("code") != "Success":
        code = body.get("code")
        msg = body.get("msg")
        raise RuntimeError(f"AutoDL API 调用失败：code={code}, msg={msg}")

    return body["data"]


def print_instance_info(data: dict) -> None:
    """打印实例详情，SSH 连接方式放在最前面、最醒目的位置。"""

    print("=" * 60)
    print("SSH 连接方式")
    print("=" * 60)
    # ssh_command 是可以直接执行的完整 SSH 登录命令，官方建议优先使用这个，
    # 不要自己用 proxy_host + ssh_port 手工拼接（字段名/格式后续可能调整）。
    print(f"ssh_command : {data.get('ssh_command')}")
    print(f"proxy_host  : {data.get('proxy_host')}")
    print(f"ssh_port    : {data.get('ssh_port')}")
    print(f"root_password: {data.get('root_password')}")

    print()
    print("=" * 60)
    print("JupyterLab")
    print("=" * 60)
    print(f"jupyter_domain: {data.get('jupyter_domain')}")
    print(f"jupyter_token : {data.get('jupyter_token')}")
    print(f"jupyter_port  : {data.get('jupyter_port')}")

    print()
    print("=" * 60)
    print("端口映射（6006 / 6008，常用于 TensorBoard / Gradio 等 Web 服务）")
    print("=" * 60)
    print(f"service_6006_domain: {data.get('service_6006_domain')}")
    print(f"service_6006_port  : {data.get('service_6006_port')}")
    print(f"service_6008_domain: {data.get('service_6008_domain')}")
    print(f"service_6008_port  : {data.get('service_6008_port')}")

    print()
    print("=" * 60)
    print("资源使用情况")
    print("=" * 60)
    usage_info = data.get("usage_info") or {}
    if usage_info.get("valid"):
        print(f"usage_info: {usage_info}")
    else:
        print("usage_info.valid 为 False —— 实例可能刚启动，监控数据还没采集到。")

    print()
    print("=" * 60)
    print("完整原始数据（供调试 / 排查未在上面单独打印的字段）")
    print("=" * 60)
    print(data)


def main() -> None:
    token = os.environ.get("AUTODL_TOKEN")
    instance_uuid = os.environ.get("AUTODL_INSTANCE_UUID")

    if not token or not instance_uuid:
        print(
            "缺少必要的环境变量。请先设置：\n"
            "  export AUTODL_TOKEN=\"your_token\"\n"
            "  export AUTODL_INSTANCE_UUID=\"pro-xxxxxxxx\"",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = get_instance_snapshot(token, instance_uuid)
    except requests.exceptions.RequestException as exc:
        print(f"HTTP 请求失败：{exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print_instance_info(data)


if __name__ == "__main__":
    main()
