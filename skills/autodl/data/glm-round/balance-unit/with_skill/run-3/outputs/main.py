#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 账户可用余额监控脚本（运维值班用）。

用法:
    AUTODL_TOKEN=<你的开发者Token> python3 main.py

行为:
    - 调用 POST https://api.autodl.com/api/v1/dev/wallet/balance 查询账户余额
    - 可用余额 = (assets - blocked_asset) / 1000，单位: 元
      注意: API 返回的金额是「元 x 1000」的整数（如 29290 = 29.29 元），
      直接把返回值当"元"展示会小 1000 倍，历史事故就是这么来的。
      冻结金额 blocked_asset 是扣掉了但不能花的钱，可用余额要减去它。
    - 可用余额低于 20 元时打印醒目告警

退出码（挂监控用）:
    0 = 正常，余额不低于阈值
    1 = 已触发低余额告警
    2 = 脚本出错，拿不到余额（视为监控失败，不要误读成"余额正常"）
"""

import os
import sys
from decimal import Decimal

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
REQUEST_TIMEOUT_SEC = 15

ALARM_THRESHOLD_YUAN = 20
# 阈值换算成 API 的整数单位（元 x 1000），比较全程用整数，避免浮点误差
ALARM_THRESHOLD_MILLI = ALARM_THRESHOLD_YUAN * 1000

EXIT_OK = 0
EXIT_LOW_BALANCE = 1
EXIT_ERROR = 2


def fail(message):
    """脚本自身出错：打印错误并以退出码 2 结束（区别于低余额告警）。"""
    print(f"[错误] {message}", file=sys.stderr, flush=True)
    sys.exit(EXIT_ERROR)


def fetch_balance_milli(token):
    """调用 AutoDL API，返回 (可用余额, 账户余额, 冻结金额)。

    三个值的单位都是「元 x 1000」的整数，保持整数避免精度问题。
    """
    # 注意: AutoDL 的鉴权头没有 Bearer 前缀，直接放 token
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": token},
            timeout=REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"请求 AutoDL API 失败: {exc}")

    if resp.status_code != 200:
        raise RuntimeError(f"API 返回 HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"API 返回的不是 JSON: {resp.text[:200]}")

    # 响应统一结构 {"code": "Success"/其他, "msg": "", "data": ...}
    if body.get("code") != "Success":
        raise RuntimeError(
            f"API 返回错误 code={body.get('code')!r} msg={body.get('msg')!r}"
        )

    data = body.get("data") or {}
    try:
        # assets: 当前余额；blocked_asset: 冻结金额（官方文档没列这个字段，
        # 但真实响应里有，取不到时按 0 处理）
        assets = int(data["assets"])
        blocked = int(data.get("blocked_asset", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"API 响应中金额字段缺失或格式异常: {data!r} ({exc})")

    return assets - blocked, assets, blocked


def yuan_str(milli):
    """把「元 x 1000」的整数精确转成元的字符串（如 29290 -> '29.29'）。

    用 Decimal 而不是 float 除法，保证打印出来的数字一位不差。
    """
    return str(Decimal(milli) / Decimal(1000))


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        fail("环境变量 AUTODL_TOKEN 未设置（Token 位置: 控制台 -> 账号 -> 设置 -> 开发者Token）")

    try:
        available_milli, assets_milli, blocked_milli = fetch_balance_milli(token)
    except RuntimeError as exc:
        fail(str(exc))

    available_yuan = yuan_str(available_milli)
    print(f"AutoDL 可用余额: {available_yuan} 元")

    if blocked_milli:
        print(f"（账户余额 {yuan_str(assets_milli)} 元，其中冻结 {yuan_str(blocked_milli)} 元不能用于消费）")

    # 阈值比较用「元 x 1000」的整数进行，20 元 = 20000，精确无浮点误差
    if available_milli < ALARM_THRESHOLD_MILLI:
        banner = "!" * 62
        print(banner)
        print("!!  [告警] AutoDL 账户可用余额不足，请立即充值！")
        print(f"!!  可用余额: {available_yuan} 元，低于告警阈值 {ALARM_THRESHOLD_YUAN} 元")
        print("!!  余额耗尽后实例会因欠费被停机，请尽快处理。")
        print(banner, flush=True)
        sys.exit(EXIT_LOW_BALANCE)

    print(f"余额正常（告警阈值 {ALARM_THRESHOLD_YUAN} 元），未触发告警。")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
