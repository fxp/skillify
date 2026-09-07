#!/usr/bin/env python3
"""AutoDL 账户余额监控脚本(运维值班用)。

查询 AutoDL 账户可用余额并按「元」打印;
可用余额低于 ALERT_THRESHOLD_YUAN 元时打印醒目告警。

接口(AutoDL 官方 API 文档 https://www.autodl.com/docs/common_api/):
    POST https://api.autodl.com/api/v1/dev/wallet/balance
    Header: Authorization: <开发者Token>   # 注意:直接填 Token,不带 "Bearer"
    返回 data.assets / data.voucher_balance 均为整数,
    单位是「毫元」:1000 = 1 元(文档注明"除以1000等于元")。
    历史事故:把原始值当成元,导致阈值差 1000 倍、告警一直不响。

退出码(便于监控平台区分状态):
    0  正常,余额不低于阈值
    2  低余额告警
    1  脚本出错(Token 缺失 / 网络失败 / 响应格式异常)
"""

import os
import sys
from decimal import Decimal

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
ALERT_THRESHOLD_YUAN = Decimal("20")
MILLI_YUAN_PER_YUAN = Decimal(1000)  # API 原始金额单位:1000 = 1 元
REQUEST_TIMEOUT_SECONDS = 15


def main() -> int:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print(
            "错误: 环境变量 AUTODL_TOKEN 未设置"
            "(Token 位置: AutoDL 控制台 -> 设置 -> 开发者 Token)",
            file=sys.stderr,
        )
        return 1

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": token},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        print(f"错误: 请求 AutoDL 接口失败: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"错误: 接口返回的不是有效 JSON: {exc}", file=sys.stderr)
        return 1

    if payload.get("code") != "Success":
        print(
            f"错误: 接口返回失败 code={payload.get('code')!r} "
            f"msg={payload.get('msg')!r}",
            file=sys.stderr,
        )
        return 1

    data = payload.get("data") or {}
    try:
        # assets 为整数,单位「毫元」,必须除以 1000 才是元,否则数值差 1000 倍
        assets_raw = int(data["assets"])
    except (KeyError, TypeError, ValueError):
        print(f"错误: 响应中没有可用的余额字段 assets: {payload!r}", file=sys.stderr)
        return 1

    # 用 Decimal 精确换算与比较,阈值判断不经过 float,数字必须准
    balance_yuan = Decimal(assets_raw) / MILLI_YUAN_PER_YUAN

    voucher_yuan = None
    try:
        voucher_yuan = Decimal(int(data["voucher_balance"])) / MILLI_YUAN_PER_YUAN
    except (KeyError, TypeError, ValueError):
        pass  # 代金券字段缺失不影响主流程

    print(f"AutoDL 可用余额: {balance_yuan:.2f} 元")
    if voucher_yuan is not None:
        print(f"(另有代金券余额: {voucher_yuan:.2f} 元,未计入上面的可用余额)")
    print(f"告警阈值: {ALERT_THRESHOLD_YUAN:.2f} 元")

    if balance_yuan < ALERT_THRESHOLD_YUAN:
        banner = "*" * 66
        print(banner)
        print("***")
        print("***            ⚠️  ⚠️  低 余 额 告 警  ⚠️  ⚠️            ***")
        print("***")
        print(f"***  可用余额 {balance_yuan:.2f} 元,已低于阈值 {ALERT_THRESHOLD_YUAN:.2f} 元!")
        print("***  请立即充值,否则实例可能因欠费被停机!")
        print("***")
        print(banner)
        return 2

    print("状态: 正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
