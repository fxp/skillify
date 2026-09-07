#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AutoDL 账户余额监控脚本（运维值班用）。

功能:
  * 调用 AutoDL 开放 API 查询账户可用余额;
  * 可用余额低于 20 元时打印醒目告警;
  * 可用余额按「元」打印。

关键单位说明（务必不要再踩坑）:
  官方接口 POST /api/v1/dev/wallet/balance 返回的 data.assets 是整数，
  单位是「千分之一元」——既不是元也不是分，官方文档原文: "除以1000等于元"
  （例: assets=1000 表示 1.00 元，assets=20000 才是 20 元）。
  因此本脚本全程用整数「千分之一元」保存金额、做阈值比较（20 元 = 20000），
  只在最后打印时才换算成元，彻底避免单位换算和浮点误差两类事故。

用法:
  AUTODL_TOKEN=你的Token python3 main.py
  （Token 获取: AutoDL 控制台 -> 设置 -> 开发者Token）

退出码（便于挂监控/告警平台判断）:
  0  正常，可用余额 >= 20 元
  1  余额告警，可用余额 < 20 元
  2  脚本自身出错（Token 未配置 / 网络失败 / API 返回异常），此时余额未知;
     注意: 2 不代表余额正常，监控应把 2 也视为需要人工介入的信号

依赖: 仅 requests
接口文档: https://www.autodl.com/docs/common_api/
"""

import os
import sys

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"
ALERT_THRESHOLD_YUAN = 20  # 告警阈值（元）: 可用余额低于该值就告警
# API 金额单位是「千分之一元」，20 元 = 20000，用整数比较避免浮点误差
ALERT_THRESHOLD_MILLI_YUAN = ALERT_THRESHOLD_YUAN * 1000
REQUEST_TIMEOUT_SECONDS = 10

EXIT_OK = 0
EXIT_LOW_BALANCE = 1
EXIT_ERROR = 2


class BalanceQueryError(Exception):
    """查询余额失败（网络、鉴权或返回格式异常）。"""


def fetch_wallet(token):
    """调用 AutoDL 余额接口，返回 data 字典（assets 已校验并统一为整数，单位: 千分之一元）。

    任何异常都抛出 BalanceQueryError，绝不返回猜测出来的余额。
    """
    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": token},  # 官方要求: 直接填 Token，不加 Bearer 前缀
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise BalanceQueryError("请求 AutoDL API 失败: {}".format(exc))

    if resp.status_code != 200:
        raise BalanceQueryError(
            "API 返回 HTTP {}，响应片段: {}".format(resp.status_code, resp.text[:200])
        )

    try:
        payload = resp.json()
    except ValueError:
        raise BalanceQueryError("API 返回的不是 JSON，响应片段: {}".format(resp.text[:200]))

    # 业务成功标志是 code 字段为字符串 "Success"（HTTP 200 不代表业务成功）
    if payload.get("code") != "Success":
        raise BalanceQueryError(
            "API 返回业务错误 code={!r} msg={!r}".format(payload.get("code"), payload.get("msg"))
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise BalanceQueryError("API 返回缺少 data 对象: {!r}".format(payload))

    # assets 即可用余额（现金余额，实例扣费用它），整数单位: 千分之一元
    assets = data.get("assets")
    if isinstance(assets, bool) or not isinstance(assets, (int, float)):
        raise BalanceQueryError("可用余额字段 data.assets 缺失或不是数字: {!r}".format(data))
    data["assets"] = int(round(assets))
    return data


def format_yuan(amount_milli_yuan):
    """把「千分之一元」的整数金额格式化成以元为单位的字符串。

    末位千分位为 0 时显示两位小数，否则显示三位，保证打印值与真实值一致，
    不会出现"打印 20.00 元却告警"这种自相矛盾的显示。
    """
    if amount_milli_yuan % 10 == 0:
        return "{:.2f}".format(amount_milli_yuan / 1000)
    return "{:.3f}".format(amount_milli_yuan / 1000)


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print(
            "错误: 未设置环境变量 AUTODL_TOKEN（获取方式: AutoDL 控制台 -> 设置 -> 开发者Token）",
            file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        wallet = fetch_wallet(token)
    except BalanceQueryError as exc:
        print(
            "错误: 查询余额失败，本次余额未知，请人工登录控制台核对! 详情: {}".format(exc),
            file=sys.stderr,
        )
        return EXIT_ERROR

    assets_milli = wallet["assets"]  # 可用余额，单位: 千分之一元
    balance_text = format_yuan(assets_milli)
    print("AutoDL 可用余额: {} 元".format(balance_text))

    # 代金券余额仅供参考展示，不参与告警判断（代金券有使用范围和有效期限制）
    voucher = wallet.get("voucher_balance")
    if isinstance(voucher, (int, float)) and not isinstance(voucher, bool):
        print("（另: 代金券余额 {} 元，不计入上面的可用余额）".format(format_yuan(int(round(voucher)))))

    # 阈值比较全程用整数（千分之一元）: 低于 20 元 <=> assets < 20000
    if assets_milli < ALERT_THRESHOLD_MILLI_YUAN:
        bar = "*" * 62
        print()
        print(bar)
        print("***  [告警][告警][告警] AutoDL 账户可用余额不足!        ***")
        print("***  当前可用余额: {} 元，低于告警阈值 {} 元".format(balance_text, ALERT_THRESHOLD_YUAN))
        print("***  请立即充值: https://www.autodl.com                ***")
        print("***  避免实例因欠费被停机!                              ***")
        print(bar)
        return EXIT_LOW_BALANCE

    print("余额正常（未低于 {} 元阈值）".format(ALERT_THRESHOLD_YUAN))
    return EXIT_OK


if __name__ == "__main__":
    # 监控/cron 环境可能是 C locale，强制 UTF-8 输出，避免中文打印报错
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
