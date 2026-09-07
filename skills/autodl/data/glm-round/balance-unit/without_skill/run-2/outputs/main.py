#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL 账户余额监控脚本（运维值班用）

功能:
  1. 调用 AutoDL 开放API 查询账户可用余额
  2. 可用余额 < 20 元时打印醒目告警
  3. 以「元」为单位打印可用余额

接口与单位说明（保证数字准确的关键）:
  - 官方文档: https://www.autodl.com/docs/common_api/
  - POST https://api.autodl.com/api/v1/dev/wallet/balance
  - 鉴权: 请求头 Authorization 直接填 API Token，不带 "Bearer" 前缀
  - 返回 data.assets 为「当前余额」整数，单位是千分之一元，除以 1000 才是元
    （文档原文备注: "当前余额。除以1000等于元"，示例 assets=1000 即 1 元）。
    本脚本用整数做阈值比较、用 Decimal 做显示换算，全程无浮点误差。

退出码（便于挂监控）:
  0 = 正常（可用余额 >= 20 元）
  2 = 余额告警（可用余额 < 20 元）
  1 = 执行出错（缺 Token / 网络失败 / 接口返回异常）
"""

import os
import sys
import time
from decimal import Decimal

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
THRESHOLD_YUAN = Decimal("20")  # 告警阈值（元）
# API 金额单位为「千分之一元」：20 元 = 20000（千分之一元）。
# 阈值先换算到与接口相同的整数单位再比较，避免任何浮点误差。
THRESHOLD_API_UNIT = 20000
TIMEOUT = 10        # 单次请求超时（秒）
MAX_RETRIES = 3     # 网络错误最大尝试次数
RETRY_INTERVAL = 2  # 重试间隔（秒）


def die(message, code=1):
    print("[错误] {}".format(message), file=sys.stderr)
    sys.exit(code)


def fetch_balance(token):
    """调用余额接口，成功时返回 data 字段（含 assets 等），失败时直接退出。"""
    headers = {"Authorization": token}  # 官方文档：Authorization 直接填 token

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            last_err = "网络/HTTP 错误: {}".format(exc)
        except ValueError as exc:
            last_err = "响应不是合法 JSON: {}".format(exc)
        else:
            if payload.get("code") != "Success":
                die("接口返回失败: code={!r} msg={!r}（请检查 AUTODL_TOKEN 是否有效）".format(
                    payload.get("code"), payload.get("msg")))
            data = payload.get("data")
            if not isinstance(data, dict) or "assets" not in data:
                die("接口返回缺少 data.assets 字段: {!r}".format(payload))
            return data

        if attempt < MAX_RETRIES:
            print("[重试] 第 {}/{} 次请求失败（{}），{}s 后重试...".format(
                attempt, MAX_RETRIES, last_err, RETRY_INTERVAL), file=sys.stderr)
            time.sleep(RETRY_INTERVAL)

    die("连续 {} 次请求余额接口失败，最后错误: {}".format(MAX_RETRIES, last_err))


def to_api_unit(value):
    """把接口返回的金额原始值统一转成整数（千分之一元），兼容 int/数字字符串。"""
    try:
        amount = Decimal(str(value))
    except Exception:
        die("余额字段不是合法数字: {!r}".format(value))
    if amount != amount.to_integral_value():
        die("余额原始值含小数，与文档不符（应为千分之一元的整数）: {!r}".format(value))
    return int(amount)


def yuan_str(api_unit_value):
    """千分之一元 -> 元 的精确字符串，固定 3 位小数（与接口精度一致）。"""
    return str((Decimal(api_unit_value) / Decimal(1000)).quantize(Decimal("0.001")))


def print_alert(assets):
    line = "*" * 60
    print(line)
    print("*" + "!!! [告警] AutoDL 账户可用余额不足 !!!" + "*" * 16)
    print(line)
    print("  当前可用余额 : {} 元".format(yuan_str(assets)))
    print("  告警阈值     : {} 元".format(yuan_str(THRESHOLD_API_UNIT)))
    print("  接口原始值   : assets = {}（单位: 千分之一元, ÷1000 = 元）".format(assets))
    print("  请立即充值，否则实例可能因欠费被强制关机！")
    print(line)


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        die("环境变量 AUTODL_TOKEN 未设置（在 AutoDL 控制台「设置 -> API 密钥」获取）")

    data = fetch_balance(token)

    assets = to_api_unit(data["assets"])  # 当前余额 = 可用余额（千分之一元）
    # 代金券余额单独展示，不参与告警判断（保守起见只看现金余额）
    voucher = to_api_unit(data.get("voucher_balance", 0) or 0)

    print("AutoDL 账户余额（接口: {}）".format(API_URL))
    print("  接口原始值   : assets = {}（单位: 千分之一元, ÷1000 = 元）".format(assets))
    print("  可用余额     : {} 元".format(yuan_str(assets)))
    print("  代金券余额   : {} 元（不计入告警阈值）".format(yuan_str(voucher)))
    print()

    # 整数域精确比较: assets < 20000（千分之一元） 等价于 可用余额 < 20.000 元
    if assets < THRESHOLD_API_UNIT:
        print_alert(assets)
        sys.exit(2)

    print("[正常] 可用余额 {} 元 >= 阈值 {} 元".format(
        yuan_str(assets), yuan_str(THRESHOLD_API_UNIT)))


if __name__ == "__main__":
    main()
