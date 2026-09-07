#!/usr/bin/env python3
"""AutoDL 账户可用余额监控脚本（供运维值班 / 监控系统调用）。

用法:
    AUTODL_TOKEN=<开发者Token> python3 main.py

功能:
    1. 查询 AutoDL 账户可用余额（现金余额，不含代金券）；
    2. 可用余额低于 20 元时打印醒目告警；
    3. 以「元」为单位打印可用余额。

接口依据（AutoDL 官方文档 https://www.autodl.com/docs/common_api/）:
    POST https://api.autodl.com/api/v1/dev/wallet/balance
    请求头 Authorization 直接填开发者 Token（无 Bearer 前缀）。
    返回 data.assets 为当前余额，单位是「千分之一元」（毫元），
    **除以 1000 才是元** —— 不是「分」（分是除以 100），切勿搞混！

金额精度（监控要求数字必须准）:
    - 告警阈值比较直接在「千分之一元」整数域进行（20 元 == 20000），
      不经过浮点除法，杜绝 19.999 / 20.0000001 之类的比较误差；
    - 展示用 Decimal 精确换算，保留 3 位小数（API 分辨率即 0.001 元，
      3 位小数无损）；同时打印接口原始值，便于人工核对单位。

退出码（便于监控平台判定）:
    0  余额正常（可用余额 >= 20 元）
    1  脚本故障（缺 Token / 网络失败 / 接口返回异常），应视为“检查失效”告警
    2  低余额告警（可用余额 < 20 元，严格低于，恰好 20.000 元不告警）
"""

import os
import sys
from decimal import Decimal

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
TOKEN_ENV = "AUTODL_TOKEN"
TIMEOUT_SECONDS = 10

# API 金额单位: 千分之一元（毫元）。1 元 = 1000，故 20 元 = 20000。
# 阈值比较统一在毫元整数域完成，避免浮点误差。
ALARM_THRESHOLD_YUAN = Decimal("20")
ALARM_THRESHOLD_MILLI_YUAN = int(ALARM_THRESHOLD_YUAN * 1000)  # -> 20000


def die(message):
    """打印脚本故障信息并以退出码 1 结束（监控应将其视为“检查失效”）。"""
    print(f"[CRITICAL] 脚本故障: {message}", file=sys.stderr)
    sys.exit(1)


def fetch_wallet_data(token):
    """调用 AutoDL 余额接口，返回响应中的 data 对象。

    其中金额字段（assets / voucher_balance 等）单位均为千分之一元，
    由调用方负责换算成元。
    """
    headers = {"Authorization": token}
    try:
        resp = requests.post(API_URL, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        die(f"请求 AutoDL 接口失败: {exc}")

    if resp.status_code != 200:
        die(f"接口返回 HTTP {resp.status_code}（401 多为 Token 错误/过期）: {resp.text[:200]!r}")

    try:
        payload = resp.json()
    except ValueError:
        die(f"接口返回不是合法 JSON: {resp.text[:200]!r}")

    if payload.get("code") != "Success":
        die(f"接口返回业务错误: code={payload.get('code')!r}, msg={payload.get('msg')!r}")

    data = payload.get("data")
    if not isinstance(data, dict):
        die(f"接口返回缺少 data 对象: {payload!r}")
    return data


def main():
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        die(f"环境变量 {TOKEN_ENV} 未设置（获取位置: 控制台 -> 设置 -> 开发者Token）")

    data = fetch_wallet_data(token)

    assets = data.get("assets")  # 当前余额（现金），单位: 千分之一元
    if isinstance(assets, bool) or not isinstance(assets, (int, float)):
        die(f"接口返回缺少/非法 assets 字段（当前余额）: {data!r}")

    # 精确换算；assets 允许为负（欠费状态），负数同样触发告警。
    balance_milli = Decimal(str(assets))
    balance_yuan = balance_milli / Decimal(1000)  # 千分之一元 -> 元，精确

    # 附注: voucher_balance 为代金券余额，同样按千分之一元计。代金券有
    # 使用范围/有效期限制，不能兜底欠费停机，故不并入可用余额、不参与
    # 告警判断，仅供参考。
    voucher_note = ""
    voucher = data.get("voucher_balance")
    if isinstance(voucher, (int, float)) and not isinstance(voucher, bool):
        voucher_yuan = Decimal(str(voucher)) / Decimal(1000)
        voucher_note = f"（另有代金券 {voucher_yuan:.3f} 元，不计入可用余额）"

    print(
        f"[AutoDL] 可用余额(现金): {balance_yuan:.3f} 元 "
        f"[原始值 assets={balance_milli} 千分之一元，÷1000=元] {voucher_note}"
    )

    if balance_milli < ALARM_THRESHOLD_MILLI_YUAN:
        print()
        print("=" * 64)
        print("!!!            余额告警 / LOW BALANCE ALERT                !!!")
        print("=" * 64)
        print(f"!!!  可用余额 {balance_yuan:.3f} 元，低于阈值 {ALARM_THRESHOLD_YUAN} 元        !!!")
        print("!!!  请立即充值，避免实例因欠费被停机、数据被清理          !!!")
        print("=" * 64)
        sys.exit(2)

    print(f"[OK] 余额正常（不低于 {ALARM_THRESHOLD_YUAN} 元）")


if __name__ == "__main__":
    main()
