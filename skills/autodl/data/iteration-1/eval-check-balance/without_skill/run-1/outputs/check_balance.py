#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询 AutoDL (autodl.com) 账户当前余额，并以“元”为单位打印。

前置条件:
    1. 登录 AutoDL 控制台，在“账号设置 -> 开发者Token（API Token）”页面获取你的 API Token。
    2. 将 Token 设置为环境变量 AUTODL_TOKEN，例如:
           export AUTODL_TOKEN="你的token"
    3. 运行:
           python3 check_balance.py

说明:
    - AutoDL 开放 API 的鉴权方式是在请求头中直接携带 Token 原文，
      即 `Authorization: <token>`，注意不是 OAuth 常见的 "Bearer <token>" 格式。
    - 本脚本只使用 Python 标准库之外的 `requests` 库直接发起 HTTP 请求，
      未使用任何 AutoDL 官方 SDK。
    - 由于本次没有可用的真实 Token/未联网验证接口的最新字段命名，
      下面的 endpoint 路径、请求方法和响应字段名是基于对 AutoDL 开放 API
      的一般认知做的“最佳猜测”实现。如果实际调用报 404 / 字段缺失，
      请对照 AutoDL 官方 API 文档 (https://www.autodl.com/docs/api_doc/)
      核对并调整 BALANCE_ENDPOINT 与 parse_balance() 中的字段名。
"""

import os
import sys

import requests

API_BASE_URL = "https://www.autodl.com"
# AutoDL 开放 API 中查询账户余额（钱包资产）的接口路径。
BALANCE_ENDPOINT = f"{API_BASE_URL}/api/v1/dev/wallet/my/balance"

REQUEST_TIMEOUT_SECONDS = 10


def get_token() -> str:
    """从环境变量 AUTODL_TOKEN 中读取 API Token。"""
    token = os.environ.get("AUTODL_TOKEN")
    if not token:
        print(
            "错误: 未找到环境变量 AUTODL_TOKEN，请先设置你的 AutoDL API Token 后再运行本脚本。\n"
            '示例: export AUTODL_TOKEN="your_token_here"',
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def fetch_balance_raw(token: str) -> dict:
    """
    调用 AutoDL 开放 API 查询账户余额信息，返回原始 JSON（dict）。

    鉴权方式: 请求头 Authorization 字段直接填入 token 本身（非 "Bearer " 前缀）。
    """
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            BALANCE_ENDPOINT,
            headers=headers,
            json={},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        print(f"请求 AutoDL API 失败（网络或连接错误）: {exc}", file=sys.stderr)
        sys.exit(1)

    if response.status_code != 200:
        print(
            f"AutoDL API 返回非 200 状态码: {response.status_code}\n响应内容: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = response.json()
    except ValueError:
        print(f"响应内容不是合法的 JSON: {response.text}", file=sys.stderr)
        sys.exit(1)

    return result


def parse_balance_in_yuan(result: dict) -> float:
    """
    从 AutoDL API 返回的 JSON 中解析出余额，并转换为“元”为单位的浮点数。

    AutoDL 接口通常以如下结构返回业务数据:
        {
            "code": "Success",
            "msg": "",
            "data": {
                "assets": 12345   # 单位: 分（1 元 = 100 分）
            }
        }

    如果业务返回码表示失败，或者找不到余额字段，将报错退出。
    """
    code = result.get("code")
    if code not in (0, "0", "Success", "success", "OK", "ok"):
        print(f"AutoDL API 返回业务错误: {result}", file=sys.stderr)
        sys.exit(1)

    data = result.get("data", {}) or {}

    # 余额字段名可能因接口版本而异，这里依次尝试几个常见候选名。
    balance_in_cents = None
    for field_name in ("assets", "balance", "amount"):
        if field_name in data:
            balance_in_cents = data[field_name]
            break

    if balance_in_cents is None:
        print(f"未能在返回数据中找到余额字段，原始返回: {result}", file=sys.stderr)
        sys.exit(1)

    # AutoDL 余额通常以“分”为最小单位返回，这里除以 100 转换为“元”。
    balance_in_yuan = balance_in_cents / 100
    return balance_in_yuan


def main() -> None:
    token = get_token()
    result = fetch_balance_raw(token)
    balance_in_yuan = parse_balance_in_yuan(result)
    print(f"当前账户余额: {balance_in_yuan:.2f} 元")


if __name__ == "__main__":
    main()
