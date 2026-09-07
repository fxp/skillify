#!/usr/bin/env python3
"""AutoDL 账户余额监控脚本（运维值班用）。

查询 AutoDL 账户的可用余额并按「元」打印；可用余额低于 20 元时打印醒目告警。

用法：
    AUTODL_TOKEN=<你的开发者Token> python3 main.py

Token 获取：AutoDL 控制台 → 账号 → 设置 → 开发者Token。

退出码（方便挂监控）：
    0 = 查询成功，余额不低于阈值
    1 = 查询成功，但余额低于阈值（已打印告警）
    2 = 查询本身失败（无 Token / 网络错误 / 接口报错 / 数据异常），
        此时余额未知，同样需要人工关注，切勿当作"余额正常"
"""

import os
import sys
from decimal import Decimal, ROUND_HALF_UP

import requests

API_URL = "https://api.autodl.com/api/v1/dev/wallet/balance"

# 告警阈值：可用余额低于 20 元即告警
THRESHOLD_YUAN = 20

# ⚠️ 单位陷阱（上次事故根源）：AutoDL 接口返回的金额字段是「元 × 1000」的整数，
# 例如 assets=29290 表示 29.29 元，官方文档原话"除以1000等于元"。
# 直接把返回的整数当"元"用，会把 29 元看成 29290 元，告警永远不响。
AMOUNT_DIVISOR = Decimal(1000)

# 阈值换算成接口原生单位（千分之一元），比较在整数域完成，避免任何浮点误差
THRESHOLD_MILLI_YUAN = THRESHOLD_YUAN * 1000  # 20000


def fetch_available_balance_milli_yuan(token):
    """调用余额接口，返回 (可用余额, 当前余额, 冻结金额)，单位均为千分之一元。

    可用余额 = assets - blocked_asset：
      - assets        当前余额（官方文档列出）
      - blocked_asset 冻结中的金额（官方文档未列，但真实响应里存在；
                      冻结的钱不能直接花，只看 assets 会高估可用额度）
    """
    # 注意：AutoDL 鉴权头没有 Bearer 前缀，直接传 token 本身
    resp = requests.post(
        API_URL,
        headers={"Authorization": token},
        timeout=15,
    )
    resp.raise_for_status()

    try:
        payload = resp.json()
    except ValueError:
        raise RuntimeError(f"接口返回的不是合法 JSON: {resp.text[:200]!r}")

    # 响应统一结构 {"code": "Success"/..., "msg": "...", "data": {...}}，code 非 Success 即出错
    if payload.get("code") != "Success":
        raise RuntimeError(
            f"接口返回错误：code={payload.get('code')!r}, msg={payload.get('msg')!r}"
        )

    data = payload.get("data") or {}
    assets = data.get("assets")
    blocked_asset = data.get("blocked_asset") or 0  # 字段缺失/为空时按无冻结处理

    if not isinstance(assets, int) or isinstance(assets, bool):
        raise RuntimeError(f"接口返回的 assets 字段缺失或不是整数: {assets!r}")
    if not isinstance(blocked_asset, int) or isinstance(blocked_asset, bool):
        raise RuntimeError(f"接口返回的 blocked_asset 字段不是整数: {blocked_asset!r}")

    available = assets - blocked_asset
    if available < 0:
        raise RuntimeError(
            f"可用余额算出负数（assets={assets}, blocked_asset={blocked_asset}），"
            "数据异常或欠费严重，请人工登录控制台核实"
        )
    return available, assets, blocked_asset


def format_yuan(milli_yuan):
    """千分之一元 → 保留两位小数（精确到分）的元数值字符串。"""
    return str(
        (Decimal(milli_yuan) / AMOUNT_DIVISOR)
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def main():
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print(
            "错误：未设置环境变量 AUTODL_TOKEN"
            "（获取路径：AutoDL 控制台 → 账号 → 设置 → 开发者Token）",
            file=sys.stderr,
        )
        return 2

    try:
        available_milli, assets_milli, blocked_milli = (
            fetch_available_balance_milli_yuan(token)
        )
    except requests.Timeout:
        print("错误：请求 AutoDL 余额接口超时", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"错误：请求 AutoDL 余额接口失败: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    # 始终把可用余额按「元」打印出来，带明确单位，保留两位小数
    print(f"AutoDL 可用余额：{format_yuan(available_milli)} 元（告警阈值 {THRESHOLD_YUAN} 元）")

    if available_milli < THRESHOLD_MILLI_YUAN:
        line = "=" * 62
        print(line)
        print("🚨🚨🚨🚨🚨  余 额 告 警  🚨🚨🚨🚨🚨")
        print(f"🚨 AutoDL 可用余额 {format_yuan(available_milli)} 元，"
              f"已低于 {THRESHOLD_YUAN} 元阈值！")
        print(f"🚨 明细：当前余额 {format_yuan(assets_milli)} 元，"
              f"冻结金额 {format_yuan(blocked_milli)} 元")
        print("🚨 请立即充值，否则实例可能因欠费被停机！")
        print(line)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
