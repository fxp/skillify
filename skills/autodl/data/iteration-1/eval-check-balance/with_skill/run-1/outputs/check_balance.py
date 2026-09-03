#!/usr/bin/env python3
"""
查询 AutoDL（autodl.com）账户当前余额，并以“元”为单位打印。

使用方法：
    export AUTODL_TOKEN="你的开发者 Token"   # 控制台 -> 账号 -> 设置 -> 开发者Token
    python3 check_balance.py

说明：
- AutoDL API 的鉴权方式比较特殊：请求头是 `Authorization: <token>`，
  没有常见的 "Bearer " 前缀，直接把 token 原样放进去即可。
- 余额接口返回的 `assets` 字段单位是“元 × 1000”的整数（例如 1000 表示 1 元），
  需要自己除以 1000 才是“元”，接口不会帮你转换。
"""

import os
import sys

import requests

AUTODL_API_BASE = "https://api.autodl.com"
BALANCE_ENDPOINT = f"{AUTODL_API_BASE}/api/v1/dev/wallet/balance"

# 从环境变量读取 token，避免把密钥写死在代码里。
# 实际使用前请先执行：export AUTODL_TOKEN="your_token_here"
AUTODL_TOKEN = os.environ.get("AUTODL_TOKEN", "your_token_here")


def get_balance_yuan(token: str) -> float:
    """调用 AutoDL 余额查询接口，返回当前余额（单位：元）。"""
    resp = requests.post(
        BALANCE_ENDPOINT,
        # 注意：AutoDL 的 Authorization 头不带 "Bearer " 前缀，直接是 token 本身。
        headers={"Authorization": token},
        timeout=10,
    )
    resp.raise_for_status()

    body = resp.json()
    if body.get("code") != "Success":
        raise RuntimeError(f"AutoDL API 返回错误：{body.get('msg')!r}（原始响应：{body}）")

    data = body.get("data", {})
    # assets 是“元 x 1000”的整数，需要除以 1000 才是“元”。
    assets_raw = data.get("assets")
    if assets_raw is None:
        raise RuntimeError(f"响应中缺少 assets 字段：{body}")

    return assets_raw / 1000


def main() -> int:
    if not AUTODL_TOKEN or AUTODL_TOKEN == "your_token_here":
        print(
            "错误：请先设置环境变量 AUTODL_TOKEN 为你的 AutoDL 开发者 Token，"
            "再运行本脚本。\n"
            "  export AUTODL_TOKEN=\"your_token_here\"",
            file=sys.stderr,
        )
        return 1

    try:
        balance_yuan = get_balance_yuan(AUTODL_TOKEN)
    except requests.exceptions.RequestException as e:
        print(f"请求 AutoDL API 失败：{e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"查询余额失败：{e}", file=sys.stderr)
        return 1

    print(f"当前账户余额：{balance_yuan:.3f} 元")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
