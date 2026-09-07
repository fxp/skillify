#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 账户可用余额监控脚本（运维值班 / 挂监控用）。

功能：
  1. 调用 AutoDL 开放 API 查询账户可用余额；
  2. 可用余额低于阈值（默认 20 元）时打印醒目告警；
  3. 无论是否告警，都把可用余额按「元」打印出来。

接口（官方文档 https://www.autodl.com/docs/common_api/ 「获取账户余额」）：
  POST https://api.autodl.com/api/v1/dev/wallet/balance
  请求头 Authorization: <开发者Token>（控制台 -> 设置 -> 开发者Token）
  成功响应形如：
    {"code": "Success", "msg": "",
     "data": {"assets": 20500, "accumulate": 1000, "voucher_balance": 1000}}

  ⚠️ 单位是这次的核心风险点：data.assets 的单位是 0.001 元（毫元），
     除以 1000 才是元，例：assets=1000 表示 1 元。
     本脚本统一用 Decimal 做精确换算，阈值比较基于毫元数值本身，
     不引入浮点运算，杜绝单位/精度导致的告警失灵。

退出码（供监控判断）：
  0 = 正常（余额不低于阈值）
  1 = 余额告警（可用余额低于阈值）
  2 = 脚本/接口错误（Token 缺失或无效、网络异常、响应格式异常等）

用法：
  AUTODL_TOKEN=你的开发者Token python3 main.py
"""

import os
import sys
from decimal import Decimal, InvalidOperation

try:
    import requests
except ImportError:
    print("错误：缺少 requests 库，请先执行：pip3 install requests", file=sys.stderr)
    sys.exit(2)

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
TIMEOUT_SECONDS = 10

# API 金额最小单位是 0.001 元（毫元）：1 元 = 1000 毫元
MILLI_PER_YUAN = Decimal(1000)

# 告警阈值：可用余额低于 20 元报警（严格小于；恰好 20.000 元不算低于，不报警）
ALARM_THRESHOLD_YUAN = Decimal("20")

EXIT_OK = 0
EXIT_ALARM = 1
EXIT_ERROR = 2


def is_below_threshold(balance_milli: Decimal) -> bool:
    """可用余额（毫元）是否低于告警阈值。直接用毫元数值比较，精确无误差。"""
    return balance_milli < ALARM_THRESHOLD_YUAN * MILLI_PER_YUAN


def to_yuan_str(balance_milli: Decimal) -> str:
    """毫元 -> 元 的字符串，保留 3 位小数（Decimal 精确换算，无浮点误差）。"""
    return str((balance_milli / MILLI_PER_YUAN).quantize(Decimal("0.001")))


def fetch_balance_milli(token: str) -> Decimal:
    """调用 AutoDL 余额接口，返回可用余额 data.assets（单位：0.001 元）。

    任何异常都抛 RuntimeError，由 main 统一打印并返回错误退出码：
    宁可 loudly failed，也不能悄悄打出错误的数字。
    """
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": token},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"请求 AutoDL 接口超时（{TIMEOUT_SECONDS} 秒）")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"请求 AutoDL 接口失败：{exc}")

    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"Token 无效或已过期（HTTP {resp.status_code}），"
            "请到 控制台 -> 设置 -> 开发者Token 重新获取"
        )
    if resp.status_code != 200:
        raise RuntimeError(f"接口返回 HTTP {resp.status_code}：{resp.text[:200]!r}")

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(f"接口返回的不是合法 JSON：{resp.text[:200]!r}")

    if payload.get("code") != "Success":
        raise RuntimeError(
            f"接口返回业务错误：code={payload.get('code')!r} "
            f"msg={payload.get('msg')!r}"
        )

    data = payload.get("data") or {}
    if "assets" not in data:
        raise RuntimeError(f"接口返回缺少 data.assets 字段：{payload!r}")

    try:
        return Decimal(str(data["assets"]))
    except (InvalidOperation, ValueError, TypeError):
        raise RuntimeError(f"data.assets 不是合法数字：{data['assets']!r}")


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print(
            "错误：环境变量 AUTODL_TOKEN 未设置"
            "（Token 获取位置：AutoDL 控制台 -> 设置 -> 开发者Token）",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        balance_milli = fetch_balance_milli(token)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_ERROR

    balance_yuan_str = to_yuan_str(balance_milli)
    threshold_yuan_str = str(ALARM_THRESHOLD_YUAN.quantize(Decimal("0.001")))

    # 始终按「元」打印可用余额，并附原始毫元值与换算过程，方便值班时核对单位
    print(f"可用余额：{balance_yuan_str} 元")
    print(
        f"（原始接口值 data.assets = {balance_milli}，"
        f"API 单位为 0.001 元，换算：{balance_milli} ÷ 1000 = {balance_yuan_str} 元）"
    )

    if is_below_threshold(balance_milli):
        gap_yuan_str = to_yuan_str(ALARM_THRESHOLD_YUAN * MILLI_PER_YUAN - balance_milli)
        banner = "*" * 66
        print(banner)
        print("!!! [告警][ALARM] AutoDL 可用余额低于阈值，请立即充值 !!!")
        print(f"    当前可用余额：{balance_yuan_str} 元")
        print(f"    告警阈值：    {threshold_yuan_str} 元")
        print(f"    距阈值缺口：  {gap_yuan_str} 元")
        print("    风险：余额耗尽后实例会因欠费被停机！")
        print(banner)
        return EXIT_ALARM

    print(
        f"[OK] AutoDL 可用余额 {balance_yuan_str} 元，"
        f"不低于告警阈值 {threshold_yuan_str} 元"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
