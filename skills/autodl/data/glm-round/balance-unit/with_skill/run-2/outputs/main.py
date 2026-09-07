#!/usr/bin/env python3
"""AutoDL 账户余额监控脚本（运维值班用）。

查询 AutoDL 账户的可用余额（单位：元），低于 20 元时打印醒目告警。
设计为被监控系统周期性执行，退出码含义：

    0 = 查询成功且余额不低于阈值
    1 = 查询成功但余额低于阈值（已触发告警）
    2 = 脚本自身出错（缺 Token / 网络失败 / API 报错）

用法：

    AUTODL_TOKEN=你的开发者Token python3 main.py

关于金额单位（重要，曾有事故）：
    AutoDL API 返回的金额是「元 × 1000」的整数，例如 29290 表示 29.29 元。
    本脚本所有阈值比较都用原始整数进行（20 元 = 20000），不经过浮点数，
    从根上避免单位/精度搞错导致告警不响。
"""

import os
import sys

import requests

BASE_URL = "https://api.autodl.com"
BALANCE_URL = f"{BASE_URL}/api/v1/dev/wallet/balance"

# 告警阈值：可用余额低于 20 元告警（「低于」= 严格小于，恰好 20 元不告警）。
# THRESHOLD_RAW 与 API 返回值同单位（元 × 1000），比较时全程整数运算。
THRESHOLD_YUAN = 20
THRESHOLD_RAW = THRESHOLD_YUAN * 1000

# 请求超时，防止监控系统被挂死
TIMEOUT_SECONDS = 15


def get_available_balance_raw(token: str) -> int:
    """调用余额接口，返回可用余额的原始整数（单位：元 × 1000）。

    可用余额 = assets（当前余额）- blocked_asset（冻结金额）。
    冻结中的钱不能直接花，只看 assets 会把余额报高。blocked_asset
    在官方文档里没列，但真实响应中存在，因此缺失时按 0 处理。

    查询失败（网络错误、HTTP 非 2xx、code != Success、字段异常）
    一律抛 RuntimeError，由调用方转成退出码 2——对监控而言，
    「查不到」必须显式暴露，不能静默当作余额为 0 或正常。
    """
    try:
        resp = requests.post(
            BALANCE_URL,
            headers={
                # AutoDL 的鉴权头没有 Bearer 前缀，直接放 token
                "Authorization": token,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"请求 AutoDL API 失败：{exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"响应不是合法 JSON：{resp.text[:200]}") from exc

    # 统一响应结构：code != "Success" 即出错，错误原因在 msg 里
    if payload.get("code") != "Success":
        raise RuntimeError(
            f"AutoDL API 返回错误：code={payload.get('code')!r}, msg={payload.get('msg')!r}"
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"响应缺少 data 对象：{payload!r}")

    assets = data.get("assets")
    blocked = data.get("blocked_asset", 0)
    if not isinstance(assets, int) or not isinstance(blocked, int):
        raise RuntimeError(f"assets/blocked_asset 字段异常：{data!r}")

    return assets - blocked


def main() -> None:
    token = os.environ.get("AUTODL_TOKEN", "").strip()
    if not token:
        print("错误：未设置环境变量 AUTODL_TOKEN（控制台 → 账号 → 设置 → 开发者Token）", file=sys.stderr)
        sys.exit(2)

    try:
        available_raw = get_available_balance_raw(token)
    except RuntimeError as exc:
        print(f"❌ 查询余额失败：{exc}", file=sys.stderr)
        sys.exit(2)

    # 换算成元仅用于展示；告警判断用的是上面的整数比较。
    # API 金额精度为 0.001 元，展示用 3 位小数，保证打印值与判断一致
    # （若用 2 位小数，19.999 元会被四舍五入显示成 20.00 元，看起来像误报）。
    available_yuan = available_raw / 1000

    if available_raw < THRESHOLD_RAW:
        print("=" * 52)
        print("🚨🚨🚨🚨🚨  AutoDL 余额告警  🚨🚨🚨🚨🚨")
        print(f"🚨 可用余额已低于 {THRESHOLD_YUAN} 元！当前：{available_yuan:.3f} 元")
        print("🚨 请立即充值，避免 GPU 实例因欠费被停机！")
        print("=" * 52)
        print(f"available_balance_yuan={available_yuan:.3f}")
        sys.exit(1)

    print(f"✅ AutoDL 可用余额正常：{available_yuan:.3f} 元（告警阈值 {THRESHOLD_YUAN} 元）")
    print(f"available_balance_yuan={available_yuan:.3f}")


if __name__ == "__main__":
    main()
