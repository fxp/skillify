#!/usr/bin/env python3
"""AutoDL 账户余额监控（运维值班用）。

查询 AutoDL 账户可用余额，低于 20 元时打印醒目告警。

用法：
    AUTODL_TOKEN=<你的开发者Token> python3 main.py

退出码（方便监控系统直接判断）：
    0  正常，可用余额 >= 20 元
    1  触发低余额告警（可用余额 < 20 元）
    2  查询失败（网络/鉴权/响应异常），此时余额未知，请勿当作"正常"

关键单位说明（防止再把单位搞错）：
    API 返回的金额字段（assets / blocked_asset）是"元 × 1000"的整数，
    例如 29290 表示 29.29 元。本脚本统一先在"毫元"整数域上做减法和
    阈值比较（20 元 = 20000），最后才换算成元展示，全程不引入浮点误差。
"""

import os
import sys
from decimal import Decimal

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
THRESHOLD_YUAN = 20          # 告警阈值（元）
THRESHOLD_MILLI = 20000      # 阈值（元 × 1000），整数比较，避免浮点误差
REQUEST_TIMEOUT = 10         # 秒。挂监控必须设超时，防止脚本挂死


def die(message: str) -> "None":
    """查询失败：醒目报错并以退出码 2 结束（区别于低余额告警）。"""
    print("=" * 52, file=sys.stderr)
    print(f"[错误] {message}", file=sys.stderr)
    print("余额查询失败，本次结果未知，请勿视为正常！", file=sys.stderr)
    print("=" * 52, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        die("环境变量 AUTODL_TOKEN 未设置或为空（控制台 → 账号 → 设置 → 开发者Token）")

    # 注意：AutoDL 的鉴权头没有 "Bearer " 前缀，直接放 token。
    headers = {"Authorization": token}

    try:
        resp = requests.post(API_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        die(f"请求 AutoDL API 失败：{exc}")

    if resp.status_code != 200:
        die(f"API 返回 HTTP {resp.status_code}：{resp.text[:200]}")

    try:
        payload = resp.json()
    except ValueError:
        die(f"API 响应不是合法 JSON：{resp.text[:200]}")

    # AutoDL 统一响应结构：{"code": "Success"/其他, "msg": "...", "data": ...}
    if payload.get("code") != "Success":
        die(f"API 返回错误 code={payload.get('code')!r} msg={payload.get('msg')!r}")

    data = payload.get("data") or {}
    assets = data.get("assets")
    if not isinstance(assets, int):
        die(f"响应中缺少整数类型的 assets 字段（当前值：{assets!r}）")

    # blocked_asset 是冻结中的金额，不能直接花；官方文档没写这个字段，
    # 但真实响应里有，缺失时按 0 处理。
    blocked = data.get("blocked_asset", 0)
    if not isinstance(blocked, int):
        die(f"blocked_asset 字段不是整数（当前值：{blocked!r}）")

    # ---- 核心计算：全部在"元 × 1000"的整数域完成，最后才换算成元 ----
    available_milli = assets - blocked            # 可用余额（元 × 1000）
    available_yuan = Decimal(available_milli) / Decimal(1000)  # 精确换算，无浮点误差
    blocked_yuan = Decimal(blocked) / Decimal(1000)
    assets_yuan = Decimal(assets) / Decimal(1000)

    if available_milli < THRESHOLD_MILLI:
        print("!" * 52)
        print("!!  [告警] AutoDL 可用余额不足 20 元！")
        print(f"!!  可用余额：{available_yuan} 元（低于阈值 20 元）")
        print(f"!!  明细：余额 {assets_yuan} 元 - 冻结 {blocked_yuan} 元")
        print("!!  账户可能因欠费被停机，请立即充值！")
        print("!" * 52)
        sys.exit(1)

    print(f"[OK] AutoDL 可用余额：{available_yuan} 元（阈值 20 元，未触发告警）")
    print(f"     明细：余额 {assets_yuan} 元 - 冻结 {blocked_yuan} 元")


if __name__ == "__main__":
    main()
